import os
import re
import secrets
import string
import tempfile
import xml.dom.minidom as md
from abc import ABC
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Callable, List, Tuple, Union
from xml.dom import minidom

import libvirt
import waiting

import consts
from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, utils
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk, DiskSourceType
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config.controller_config import BaseNodeConfig
from service_client import log


class LibvirtController(NodeController, ABC):
    TEST_DISKS_PREFIX = "ua-TestInfraDisk"

    def __init__(self, config: BaseNodeConfig, entity_config: Union[BaseClusterConfig, BaseInfraEnvConfig]):
        super().__init__(config, entity_config)
        self.libvirt_connection: libvirt.virConnect = libvirt.open("qemu:///system")
        self.private_ssh_key_path: Path = config.private_ssh_key_path
        self._setup_timestamp: str = utils.run_command('date +"%Y-%m-%d %T"')[0]

    def __del__(self):
        with suppress(Exception):
            self.libvirt_connection.close()

    @staticmethod
    @contextmanager
    def connection_context():
        conn = libvirt.open("qemu:///system")
        try:
            yield conn
        finally:
            conn.close()

    @property
    def setup_time(self):
        return self._setup_timestamp

    def list_nodes(self) -> List[Node]:
        return self.list_nodes_with_name_filter(None)

    def list_nodes_with_name_filter(self, name_filter) -> List[Node]:
        log.info("Listing current hosts with name filter %s", name_filter)
        nodes = list()

        domains = self.libvirt_connection.listAllDomains()
        for domain in domains:
            domain_name = domain.name()
            if name_filter and name_filter not in domain_name:
                continue
            if (consts.NodeRoles.MASTER in domain_name) or (consts.NodeRoles.WORKER in domain_name):
                nodes.append(Node(domain_name, self, self.private_ssh_key_path))

        log.info("Found domains %s", [node.name for node in nodes])
        return nodes

    def list_networks(self):
        return self.libvirt_connection.listAllNetworks()

    @classmethod
    def _list_disks(cls, node):
        all_disks = minidom.parseString(node.XMLDesc()).getElementsByTagName("disk")
        return [cls._disk_xml_to_disk_obj(disk_xml) for disk_xml in all_disks]

    @classmethod
    def _disk_xml_to_disk_obj(cls, disk_xml):
        return Disk(
            # device_type indicates how the disk is to be exposed to the guest OS.
            # Possible values for this attribute are "floppy", "disk", "cdrom", and "lun", defaulting to "disk".
            type=disk_xml.getAttribute("device"),
            alias=cls._get_disk_alias(disk_xml),
            wwn=cls._get_disk_wwn(disk_xml),
            **cls._get_disk_source_attributes(disk_xml),
            **cls._get_disk_target_data(disk_xml),
        )

    @staticmethod
    def _get_disk_source_attributes(disk_xml):
        source_xml = disk_xml.getElementsByTagName("source")

        source_type = DiskSourceType.OTHER
        source_path = None
        source_pool = None
        source_volume = None

        if source_xml:
            disk_type = disk_xml.getAttribute("type")
            source_element = source_xml[0]

            if disk_type == "file":
                source_type = DiskSourceType.FILE
                source_path = source_element.getAttribute("file")
            elif disk_type == "block":
                source_type = DiskSourceType.BLOCK
                source_path = source_element.getAttribute("dev")
            elif disk_type == "dir":
                source_type = DiskSourceType.DIR
                source_path = source_element.getAttribute("dir")
            elif disk_type == "network":
                source_type = DiskSourceType.NETWORK
            elif disk_type == "volume":
                source_type = DiskSourceType.VOLUME
                source_pool = source_element.getAttribute("pool")
                source_volume = source_element.getAttribute("volume")
            elif disk_type == "nvme":
                source_type = DiskSourceType.NVME

        return dict(
            source_type=source_type,
            source_path=source_path,
            source_pool=source_pool,
            source_volume=source_volume,
        )

    @staticmethod
    def _get_disk_target_data(disk_xml):
        target_xml = disk_xml.getElementsByTagName("target")
        return dict(
            bus=target_xml[0].getAttribute("bus") if target_xml else None,
            target=target_xml[0].getAttribute("dev") if target_xml else None,
        )

    @staticmethod
    def _get_disk_wwn(disk_xml):
        wwn_xml = disk_xml.getElementsByTagName("wwn")
        wwn = wwn_xml[0].firstChild.data if wwn_xml else None
        return wwn

    @staticmethod
    def _get_disk_alias(disk_xml):
        alias_xml = disk_xml.getElementsByTagName("alias")
        alias = alias_xml[0].getAttribute("name") if alias_xml else None
        return alias

    def list_disks(self, node_name: str):
        node = self.libvirt_connection.lookupByName(node_name)
        return self._list_disks(node)

    def list_leases(self, network_name):
        with utils.file_lock_context():
            net = self.libvirt_connection.networkLookupByName(network_name)
            leases = net.DHCPLeases()  # TODO: getting the information from the XML dump until dhcp-leases bug is fixed
            hosts = self._get_hosts_from_network(net)
            return leases + [h for h in hosts if h["ipaddr"] not in [ls["ipaddr"] for ls in leases]]

    @staticmethod
    def _get_hosts_from_network(net):
        desc = md.parseString(net.XMLDesc())
        try:
            hosts = (
                desc.getElementsByTagName("network")[0]
                .getElementsByTagName("ip")[0]
                .getElementsByTagName("dhcp")[0]
                .getElementsByTagName("host")
            )
            return list(
                map(
                    lambda host: {
                        "mac": host.getAttribute("mac"),
                        "ipaddr": host.getAttribute("ip"),
                        "hostname": host.getAttribute("name"),
                    },
                    hosts,
                )
            )
        except IndexError:
            return []

    def wait_till_nodes_are_ready(self, network_name):
        log.info("Wait till %s nodes will be ready and have ips", self._config.nodes_count)
        try:
            waiting.wait(
                lambda: len(self.list_leases(network_name)) >= self._config.nodes_count,
                timeout_seconds=consts.NODES_REGISTERED_TIMEOUT * self._config.nodes_count,
                sleep_seconds=10,
                waiting_for="Nodes to have ips",
            )
            log.info("All nodes have booted and got ips")
        except BaseException:
            log.error(
                "Not all nodes are ready. Current dhcp leases are %s",
                self.list_leases(network_name),
            )
            raise

    def shutdown_node(self, node_name):
        log.info("Going to shutdown %s", node_name)
        node = self.libvirt_connection.lookupByName(node_name)

        if node.isActive():
            node.destroy()

    def shutdown_all_nodes(self):
        log.info("Going to shutdown all the nodes")
        nodes = self.list_nodes()

        for node in nodes:
            self.shutdown_node(node.name())

    def start_node(self, node_name, check_ips=True):
        log.info("Going to power-on %s, check ips flag %s", node_name, check_ips)
        node = self.libvirt_connection.lookupByName(node_name)

        if not node.isActive():
            try:
                node.create()
                if check_ips:
                    self._wait_till_domain_has_ips(node)
            except waiting.exceptions.TimeoutExpired:
                log.warning("Node %s failed to recive IP, retrying", node_name)
                self.shutdown_node(node_name)
                node.create()
                if check_ips:
                    self._wait_till_domain_has_ips(node)

    def start_all_nodes(self):
        log.info("Going to power-on all the nodes")
        nodes = self.list_nodes()

        for node in nodes:
            self.start_node(node.name())
        return nodes

    @staticmethod
    def create_disk(disk_path, disk_size):
        command = f"qemu-img create -f qcow2 {disk_path} {disk_size}"
        utils.run_command(command, shell=True)

    @staticmethod
    # LIBGUESTFS_BACKEND set to mitigate errors with running libvirt as root
    # https://libguestfs.org/guestfs-faq.1.html#permission-denied-when-running-libguestfs-as-root
    def add_disk_bootflag(disk_path):
        command = f"virt-format -a {disk_path} --partition=mbr"
        utils.run_command(command, shell=True, env={**os.environ, "LIBGUESTFS_BACKEND": "direct"})

    @classmethod
    def format_disk(cls, disk_path):
        log.info("Formatting disk %s", disk_path)
        if not os.path.exists(disk_path):
            log.info("Path to %s disk not exists. Skipping", disk_path)
            return

        command = f"qemu-img info {disk_path} | grep 'virtual size'"
        output = utils.run_command(command, shell=True)
        image_size = output[0].split(" ")[2]
        # Fix for libvirt 6.0.0
        if image_size.isdigit():
            image_size += "G"

        cls.create_disk(disk_path, image_size)

    @classmethod
    def _get_all_scsi_disks(cls, node):
        return (disk for disk in cls._list_disks(node) if disk.bus == "scsi")

    @classmethod
    def _get_attached_test_disks(cls, node):
        return (
            disk
            for disk in cls._get_all_scsi_disks(node)
            if disk.alias and disk.alias.startswith(cls.TEST_DISKS_PREFIX)
        )

    @staticmethod
    def _get_disk_scsi_identifier(disk):
        """
        :return: Returns `b` if, for example, the disks' target.dev is `sdb`
        """
        return re.findall(r"^sd(.*)$", disk.target)[0]

    def _get_available_scsi_identifier(self, node):
        """
        :return: Returns, for example, `d` if `sda`, `sdb`, `sdc`, `sde` are all already in use
        """
        identifiers_in_use = [self._get_disk_scsi_identifier(disk) for disk in self._get_all_scsi_disks(node)]

        try:
            result = next(candidate for candidate in string.ascii_lowercase if candidate not in identifiers_in_use)
        except StopIteration as e:
            raise ValueError(f"Couldn't find available scsi disk letter, all are taken: {identifiers_in_use}") from e

        return result

    def attach_test_disk(self, node_name, disk_size, bootable=False, persistent=False, with_wwn=False):
        """
        Attaches a disk with the given size to the given node. All tests disks can later
        be detached with detach_all_test_disks
        """
        node = self.libvirt_connection.lookupByName(node_name)

        # Prefixing the disk's target element's dev attribute with `sd` makes libvirt create an SCSI disk.
        # We don't use `vd` virtio disks because libvirt overwrites our aliases if we do so, coming up with
        # its own `virtio-<num>` aliases instead. Those aliases allow us to identify disks created by this
        # function when we perform `detach_all_test_disks` for cleanup.
        target_dev = f"sd{self._get_available_scsi_identifier(node)}"
        disk_alias = f"{self.TEST_DISKS_PREFIX}-{target_dev}"

        with tempfile.NamedTemporaryFile() as f:
            tmp_disk = f.name

        self.create_disk(tmp_disk, disk_size)

        if bootable:
            self.add_disk_bootflag(tmp_disk)

        attach_flags = libvirt.VIR_DOMAIN_AFFECT_LIVE

        if persistent:
            attach_flags |= libvirt.VIR_DOMAIN_AFFECT_CONFIG

        wwn = f"<wwn>0x{secrets.token_hex(8)}</wwn>" if with_wwn else ""

        node.attachDeviceFlags(
            f"""
            <disk type='file' device='disk'>
                <alias name='{disk_alias}'/>
                <driver name='qemu' type='qcow2'/>
                <source file='{tmp_disk}'/>
                <target dev='{target_dev}'/>
                {wwn}
            </disk>
        """,
            attach_flags,
        )

        return tmp_disk

    def detach_all_test_disks(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)

        for test_disk in self._get_attached_test_disks(node):
            assert test_disk.alias is not None, "A test disk has no alias. This should never happen"
            node.detachDeviceAlias(test_disk.alias)

            assert test_disk.source_path is not None, "A test disk has no source file. This should never happen"
            assert test_disk.source_path.startswith(
                tempfile.gettempdir()
            ), "File unexpectedly not in tmp, avoiding deletion to be on the safe side"
            os.remove(test_disk.source_path)

    def attach_interface(self, node_name, network_xml, target_interface=consts.TEST_TARGET_INTERFACE):
        """
        Create network and Interface. New interface will be attached to a given node.
        """
        network = self.create_network(network_xml)
        interface_mac = self.add_interface(node_name, network.bridgeName(), target_interface)
        return network, interface_mac

    def create_network(self, network_xml):
        """
        Create a network from a given xml and return libvirt.virNetwork object
        """
        log.info(f"Creating new network: {network_xml}")
        network = self.libvirt_connection.networkCreateXML(network_xml)
        if network is None:
            raise Exception(f"Failed to create network: {network_xml}")
        active = network.isActive()
        if active != 1:
            self.destroy_network(network)
            raise Exception(f"Failed to activate network: {network_xml}")
        log.info(f"Successfully created and activated network. name: {network.name()}")
        return network

    def get_network_by_name(self, network_name):
        """
        Get network name and return libvirt.virNetwork object
        """
        return self.libvirt_connection.networkLookupByName(network_name)

    def destroy_network(self, network):
        """
        Destroy network of a given libvirt.virNetwork object
        """
        log.info(f"Destroy network: {network.name()}")
        network.destroy()

    def add_interface(self, node_name, network_name, target_interface):
        """
        Create an interface using given network name, return created interface's mac address.
        Note: Do not use the same network for different tests
        """
        log.info(f"Creating new interface attached to network: {network_name}, for node: {node_name}")
        net_leases = self.list_leases(network_name)
        mac_addresses = []
        for lease in net_leases:
            mac_addresses.append(lease["mac"])
        command = f"virsh attach-interface {node_name} network {network_name} --target {target_interface} --persistent"
        utils.run_command(command)
        try:
            waiting.wait(
                lambda: len(self.list_leases(network_name)) > len(mac_addresses),
                timeout_seconds=30,
                sleep_seconds=2,
                waiting_for="Wait for network lease",
            )
        except waiting.exceptions.TimeoutExpired:
            log.error("Network lease wasnt found for added interface")
            raise

        mac_address = ""
        new_net_leases = self.list_leases(network_name)
        for lease in new_net_leases:
            if not lease["mac"] in mac_addresses:
                mac_address = lease["mac"]
                break
        log.info(
            f"Successfully attached interface, network: {network_name}, mac: {mac_address}, for node:" f" {node_name}"
        )
        return mac_address

    def undefine_interface(self, node_name, mac):
        log.info(f"Undefining an interface mac: {mac}, for node: {node_name}")
        command = f"virsh detach-interface {node_name} --type network --mac {mac}"
        utils.run_command(command, True)
        log.info("Successfully removed interface.")

    def restart_node(self, node_name):
        log.info("Restarting %s", node_name)
        self.shutdown_node(node_name=node_name)
        self.start_node(node_name=node_name)

    def format_all_node_disks(self):
        log.info("Formatting all the disks")
        nodes = self.list_nodes()

        for node in nodes:
            self.format_node_disk(node.name())

    def prepare_nodes(self):
        self.destroy_all_nodes()

    def destroy_all_nodes(self):
        log.info("Delete all the nodes")
        self.shutdown_all_nodes()
        self.format_all_node_disks()

    def is_active(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)
        return node.isActive()

    def get_node_ips_and_macs(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)
        return self._get_domain_ips_and_macs(node)

    @staticmethod
    def _get_domain_ips_and_macs(domain: libvirt.virDomain) -> Tuple[List[str], List[str]]:
        interfaces_sources = [
            # getting all DHCP leases IPs
            libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE,
            # getting static IPs via ARP
            libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP,
        ]

        interfaces = {}
        for addresses_source in interfaces_sources:
            try:
                interfaces.update(**domain.interfaceAddresses(addresses_source))
            except libvirt.libvirtError:
                log.exception("Got an error while updating domain's network addresses")

        ips = []
        macs = []
        log.debug(f"Host {domain.name()} interfaces are {interfaces}")
        if interfaces:
            for (_, val) in interfaces.items():
                if val["addrs"]:
                    for addr in val["addrs"]:
                        ips.append(addr["addr"])
                        macs.append(val["hwaddr"])
        if ips:
            log.info("Host %s ips are %s", domain.name(), ips)
        if macs:
            log.info("Host %s macs are %s", domain.name(), macs)
        return ips, macs

    def _get_domain_ips(self, domain):
        ips, _ = self._get_domain_ips_and_macs(domain)
        return ips

    def _wait_till_domain_has_ips(self, domain, timeout=600, interval=10):
        log.info("Waiting till host %s will have ips", domain.name())
        waiting.wait(
            lambda: len(self._get_domain_ips(domain)) > 0,
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Waiting for Ips",
            expected_exceptions=Exception,
        )

    @staticmethod
    def _clean_domain_os_boot_data(node_xml):
        os_element = node_xml.getElementsByTagName("os")[0]

        for el in os_element.getElementsByTagName("boot"):
            dev = el.getAttribute("dev")
            if dev in ["cdrom", "hd"]:
                os_element.removeChild(el)
            else:
                raise ValueError(f"Found unexpected boot device: '{dev}'")

        for disk in node_xml.getElementsByTagName("disk"):
            for boot in disk.getElementsByTagName("boot"):
                disk.removeChild(boot)

    def set_per_device_boot_order(self, node_name, key: Callable[[Disk], int]):
        log.info(f"Changing boot order for node: {node_name}")
        node = self.libvirt_connection.lookupByName(node_name)
        current_xml = node.XMLDesc(0)
        xml = minidom.parseString(current_xml.encode("utf-8"))
        self._clean_domain_os_boot_data(xml)
        disks_xmls = xml.getElementsByTagName("disk")
        disks_xmls.sort(key=lambda disk: key(self._disk_xml_to_disk_obj(disk)))

        for index, disk_xml in enumerate(disks_xmls):
            boot_element = xml.createElement("boot")
            boot_element.setAttribute("order", str(index + 1))
            disk_xml.appendChild(boot_element)

        # Apply new machine xml
        dom = self.libvirt_connection.defineXML(xml.toprettyxml())
        if dom is None:
            raise Exception(f"Failed to set boot order for node: {node_name}")
        log.info(f"Boot order set successfully: for node: {node_name}")
        # After setting per-device boot order, we have to shutdown the guest(reboot isn't enough)
        log.info(f"Restarting node {node_name} to allow boot changes to take effect")
        self.shutdown_node(node_name)
        self.start_node(node_name)

    def set_boot_order(self, node_name, cd_first=False):
        log.info(f"Going to set the following boot order: cd_first: {cd_first}, " f"for node: {node_name}")
        node = self.libvirt_connection.lookupByName(node_name)
        current_xml = node.XMLDesc(0)
        xml = minidom.parseString(current_xml.encode("utf-8"))
        self._clean_domain_os_boot_data(xml)
        os_element = xml.getElementsByTagName("os")[0]
        # Set boot elements for hd and cdrom
        first = xml.createElement("boot")
        first.setAttribute("dev", "cdrom" if cd_first else "hd")
        os_element.appendChild(first)
        second = xml.createElement("boot")
        second.setAttribute("dev", "hd" if cd_first else "cdrom")
        os_element.appendChild(second)
        # Apply new machine xml
        dom = self.libvirt_connection.defineXML(xml.toprettyxml())
        if dom is None:
            raise Exception(f"Failed to set boot order cdrom first: {cd_first}, for node: {node_name}")
        log.info(f"Boot order set successfully: cdrom first: {cd_first}, for node: {node_name}")

    def get_host_id(self, node_name):
        dom = self.libvirt_connection.lookupByName(node_name)
        return dom.UUIDString()

    def get_cpu_cores(self, node_name):
        xml = self._get_xml(node_name)
        vcpu_element = xml.getElementsByTagName("vcpu")[0]
        return int(vcpu_element.firstChild.nodeValue)

    def set_cpu_cores(self, node_name, core_count):
        log.info(f"Going to set vcpus to {core_count} for node: {node_name}")
        dom = self.libvirt_connection.lookupByName(node_name)
        dom.setVcpusFlags(core_count)
        log.info(f"Successfully set vcpus to {core_count} for node: {node_name}")

    def get_ram_kib(self, node_name):
        xml = self._get_xml(node_name)
        memory_element = xml.getElementsByTagName("currentMemory")[0]
        return int(memory_element.firstChild.nodeValue)

    def set_ram_kib(self, node_name, ram_kib):
        log.info(f"Going to set memory to {ram_kib} for node: {node_name}")
        xml = self._get_xml(node_name)
        memory_element = xml.getElementsByTagName("memory")[0]
        memory_element.firstChild.replaceWholeText(ram_kib)
        current_memory_element = xml.getElementsByTagName("currentMemory")[0]
        current_memory_element.firstChild.replaceWholeText(ram_kib)
        dom = self.libvirt_connection.defineXML(xml.toprettyxml())
        if dom is None:
            raise Exception(f"Failed to set memory for node: {node_name}")
        log.info(f"Successfully set memory to {ram_kib} for node: {node_name}")

    def _get_xml(self, node_name):
        dom = self.libvirt_connection.lookupByName(node_name)
        current_xml = dom.XMLDesc(0)
        return minidom.parseString(current_xml.encode("utf-8"))

    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        raise NotImplementedError

    def get_ingress_and_api_vips(self) -> dict:
        raise NotImplementedError

    def get_cluster_network(self) -> str:
        raise NotImplementedError

    def set_single_node_ip(self, ip):
        raise NotImplementedError
