import os
import re
import string
import logging
import tempfile
from abc import ABC
from typing import List

import libvirt
import waiting
from xml.dom import minidom
from contextlib import suppress

from test_infra import utils
from test_infra import consts
from test_infra.controllers.node_controllers.node_controller import NodeController


class LibvirtController(NodeController, ABC):
    TEST_DISKS_PREFIX = "ua-TestInfraDisk"

    def __init__(self, **kwargs):
        self.libvirt_connection = libvirt.open('qemu:///system')
        self.private_ssh_key_path = kwargs.get("private_ssh_key_path")
        self._setup_timestamp = utils.run_command("date +\"%Y-%m-%d %T\"")[0]

    def __del__(self):
        with suppress(Exception):
            self.libvirt_connection.close()

    @property
    def setup_time(self):
        return self._setup_timestamp

    def list_nodes(self) -> List[libvirt.virDomain]:
        return self.list_nodes_with_name_filter(None)

    def list_nodes_with_name_filter(self, name_filter) -> List[libvirt.virDomain]:
        logging.info("Listing current hosts with name filter %s", name_filter)
        nodes = []
        domains = self.libvirt_connection.listAllDomains()
        for domain in domains:
            domain_name = domain.name()
            if name_filter and name_filter not in domain_name:
                continue
            if (consts.NodeRoles.MASTER in domain_name) or (consts.NodeRoles.WORKER in domain_name):
                nodes.append(domain)
        logging.info("Found domains %s", nodes)
        return nodes

    def list_networks(self):
        return self.libvirt_connection.listAllNetworks()

    def list_leases(self, network_name):
        return self.libvirt_connection.networkLookupByName(network_name).DHCPLeases()

    def shutdown_node(self, node_name):
        logging.info("Going to shutdown %s", node_name)
        node = self.libvirt_connection.lookupByName(node_name)

        if node.isActive():
            node.destroy()

    def shutdown_all_nodes(self):
        logging.info("Going to shutdown all the nodes")
        nodes = self.list_nodes()

        for node in nodes:
            self.shutdown_node(node.name())

    def start_node(self, node_name, check_ips):
        logging.info("Going to power-on %s, check ips flag %s", node_name, check_ips)
        node = self.libvirt_connection.lookupByName(node_name)

        if not node.isActive():
            try:
                node.create()
                if check_ips:
                    self._wait_till_domain_has_ips(node)
            except waiting.exceptions.TimeoutExpired:
                logging.warning("Node %s failed to recive IP, retrying", node_name)
                self.shutdown_node(node_name)
                node.create()
                if check_ips:
                    self._wait_till_domain_has_ips(node)

    def start_all_nodes(self):
        logging.info("Going to power-on all the nodes")
        nodes = self.list_nodes()

        for node in nodes:
            self.start_node(node.name())
        return nodes

    @staticmethod
    def create_disk(disk_path, disk_size):
        command = f'qemu-img create -f qcow2 {disk_path} {disk_size}'
        utils.run_command(command, shell=True)

    @staticmethod
    # LIBGUESTFS_BACKEND set to mitigate errors with running libvirt as root
    # https://libguestfs.org/guestfs-faq.1.html#permission-denied-when-running-libguestfs-as-root
    def add_disk_bootflag(disk_path):
        command = f'virt-format -a {disk_path} --partition=mbr'
        utils.run_command(command, shell=True, env={**os.environ, "LIBGUESTFS_BACKEND": "direct"})

    @classmethod
    def format_disk(cls, disk_path):
        logging.info("Formatting disk %s", disk_path)
        if not os.path.exists(disk_path):
            logging.info("Path to %s disk not exists. Skipping", disk_path)
            return

        command = f"qemu-img info {disk_path} | grep 'virtual size'"
        output = utils.run_command(command, shell=True)
        image_size = output[0].split(' ')[2]
        # Fix for libvirt 6.0.0
        if image_size.isdigit():
            image_size += "G"

        cls.create_disk(disk_path, image_size)

    @staticmethod
    def _get_all_scsi_disks(node):
        """
        :return: All node disks that use an SCSI bus (/dev/sd*)
        """
        def is_scsi_disk(disk):
            return any(target.getAttribute('bus') == 'scsi' for target in
                       disk.getElementsByTagName('target'))

        all_disks = minidom.parseString(node.XMLDesc()).getElementsByTagName('disk')

        return [disk for disk in all_disks if is_scsi_disk(disk)]

    @staticmethod
    def _get_disk_source_file(disk):
        sources = disk.getElementsByTagName('source')

        assert len(sources) in (0, 1), f"A disk must have either 0 or 1 sources, {sources}"

        if len(sources) == 0:
            return None

        return sources[0].getAttribute('file')

    @staticmethod
    def _get_disk_alias(disk):
        aliases = disk.getElementsByTagName('alias')

        assert len(aliases) in (0, 1), f"A disk must have either 0 or 1 aliases, {aliases}"

        if len(aliases) == 0:
            return None

        return aliases[0].getAttribute('name')

    @classmethod
    def _get_attached_test_disks(cls, node):
        """
        :return: Returns all disks created by `self.attach_test_disk` by examining the alias of all SCSI disks
        """
        def is_test_disk(disk):
            return any(alias.getAttribute('name').startswith(cls.TEST_DISKS_PREFIX) for alias in
                       disk.getElementsByTagName('alias'))

        all_scsi_disks = cls._get_all_scsi_disks(node)

        return [disk for disk in all_scsi_disks if is_test_disk(disk)]

    @staticmethod
    def _get_disk_scsi_identifier(disk):
        """
        :return: Returns `b` if, for example, the disks' target.dev is `sdb`
        """
        target_elements = disk.getElementsByTagName('target')
        assert len(target_elements) == 1, f"Disks shouldn't have multiple targets, {target_elements}"
        target_element = target_elements[0]

        return re.findall(r"^sd(.*)$", target_element.getAttribute('dev'))[0]

    def _get_available_scsi_identifier(self, node):
        """
        :return: Returns, for example, `d` if `sda`, `sdb`, `sdc`, `sde` are all already in use
        """
        identifiers_in_use = [self._get_disk_scsi_identifier(disk) for disk in self._get_all_scsi_disks(node)]

        try:
            result = next(candidate for candidate in string.ascii_lowercase if candidate not in identifiers_in_use)
        except StopIteration:
            raise ValueError(f"Couldn't find available scsi disk letter, all are taken: {identifiers_in_use}")

        return result

    def attach_test_disk(self, node_name, disk_size, bootable=False):
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

        node.attachDevice(f"""
            <disk type='file' device='disk'>
                <alias name='{disk_alias}'/>
                <driver name='qemu' type='qcow2'/>
                <source file='{tmp_disk}'/>
                <target dev='{target_dev}'/>
            </disk>
        """)

        return tmp_disk

    def detach_all_test_disks(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)

        for test_disk in self._get_attached_test_disks(node):
            alias = self._get_disk_alias(test_disk)
            assert alias is not None, "A test disk has no alias. This should never happen"
            node.detachDeviceAlias(alias)

            source_file = self._get_disk_source_file(test_disk)
            assert source_file is not None, "A test disk has no source file. This should never happen"
            assert source_file.startswith(
                tempfile.gettempdir()), "File unexpectedly not in tmp, avoiding deletion to be on the safe side"
            os.remove(source_file)

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
        logging.info(f"Creating new network: {network_xml}")
        network = self.libvirt_connection.networkCreateXML(network_xml)
        if network is None:
            raise Exception(f"Failed to create network: {network_xml}")
        active = network.isActive()
        if active != 1:
            self.destroy_network(network)
            raise Exception(f"Failed to activate network: {network_xml}")
        logging.info(f"Successfully created and activated network. name: {network.name()}")
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
        logging.info(f"Destroy network: {network.name()}")
        network.destroy()

    def add_interface(self, node_name, network_name, target_interface):
        """
        Create an interface using given network name, return created interface's mac address.
        Note: Do not use the same network for different tests
        """
        logging.info(f"Creating new interface attached to network: {network_name}, for node: {node_name}")
        net_leases = self.list_leases(network_name)
        mac_addresses = []
        for lease in net_leases:
            mac_addresses.append(lease['mac'])
        command = f"virsh attach-interface {node_name} network {network_name} --target {target_interface} --persistent"
        utils.run_command(command)
        try:
            waiting.wait(
                    lambda: len(self.list_leases(network_name)) > len(mac_addresses),
                    timeout_seconds=30,
                    sleep_seconds=2,
                    waiting_for="Wait for network lease"
            )
        except waiting.exceptions.TimeoutExpired:
            logging.error("Network lease wasnt found for added interface")
            raise

        new_net_leases = self.list_leases(network_name)
        for lease in new_net_leases:
            if not lease['mac'] in mac_addresses:
                mac_address = lease['mac']
                break
        logging.info(f"Successfully attached interface, network: {network_name}, mac: {mac_address}, for node:"
                     f" {node_name}")
        return mac_address

    def undefine_interface(self, node_name, mac):
        logging.info(f"Undefining an interface mac: {mac}, for node: {node_name}")
        command = f"virsh detach-interface {node_name} --type network --mac {mac}"
        utils.run_command(command, True)
        logging.info(f"Successfully removed interface.")

    def restart_node(self, node_name):
        logging.info("Restarting %s", node_name)
        self.shutdown_node(node_name=node_name)
        self.start_node(node_name=node_name)

    def format_all_node_disks(self):
        logging.info("Formatting all the disks")
        nodes = self.list_nodes()

        for node in nodes:
            self.format_node_disk(node.name())

    def prepare_nodes(self):
        self.destroy_all_nodes()

    def destroy_all_nodes(self):
        logging.info("Delete all the nodes")
        self.shutdown_all_nodes()
        self.format_all_node_disks()

    def is_active(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)
        return node.isActive()

    def get_node_ips_and_macs(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)
        return self._get_domain_ips_and_macs(node)

    @staticmethod
    def _get_domain_ips_and_macs(domain):
        interfaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)
        ips = []
        macs = []
        if interfaces:
            for (_, val) in interfaces.items():
                if val['addrs']:
                    for addr in val['addrs']:
                        ips.append(addr['addr'])
                        macs.append(val['hwaddr'])
        if ips:
            logging.info("Host %s ips are %s", domain.name(), ips)
        if macs:
            logging.info("Host %s macs are %s", domain.name(), macs)
        return ips, macs

    def _get_domain_ips(self, domain):
        ips, _ = self._get_domain_ips_and_macs(domain)
        return ips

    def _wait_till_domain_has_ips(self, domain, timeout=360, interval=5):
        logging.info("Waiting till host %s will have ips", domain.name())
        waiting.wait(
            lambda: len(self._get_domain_ips(domain)) > 0,
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Waiting for Ips",
            expected_exceptions=Exception
        )

    def set_boot_order(self, node_name, cd_first=False):
        logging.info(f"Going to set the following boot order: cd_first: {cd_first}, "
                     f"for node: {node_name}")
        node = self.libvirt_connection.lookupByName(node_name)
        current_xml = node.XMLDesc(0)
        # Creating XML obj
        xml = minidom.parseString(current_xml.encode('utf-8'))
        os_element = xml.getElementsByTagName('os')[0]
        # Delete existing boot elements
        for el in os_element.getElementsByTagName('boot'):
            dev = el.getAttribute('dev')
            if dev in ['cdrom', 'hd']:
                os_element.removeChild(el)
            else:
                raise ValueError(f'Found unexpected boot device: \'{dev}\'')
        # Set boot elements for hd and cdrom
        first = xml.createElement('boot')
        first.setAttribute('dev', 'cdrom' if cd_first else 'hd')
        os_element.appendChild(first)
        second = xml.createElement('boot')
        second.setAttribute('dev', 'hd' if cd_first else 'cdrom')
        os_element.appendChild(second)
        # Apply new machine xml
        dom = self.libvirt_connection.defineXML(xml.toprettyxml())
        if dom is None:
            raise Exception(f"Failed to set boot order cdrom first: {cd_first}, "
                            f"for node: {node_name}")
        logging.info(f"Boot order set successfully: cdrom first: {cd_first}, "
                     f"for node: {node_name}")

    def get_host_id(self, node_name):
        dom = self.libvirt_connection.lookupByName(node_name)
        return dom.UUIDString()

    def get_cpu_cores(self, node_name):
        xml = self._get_xml(node_name)
        vcpu_element = xml.getElementsByTagName('vcpu')[0]
        return int(vcpu_element.firstChild.nodeValue)

    def set_cpu_cores(self, node_name, core_count):
        logging.info(f"Going to set vcpus to {core_count} for node: {node_name}")
        dom = self.libvirt_connection.lookupByName(node_name)
        dom.setVcpusFlags(core_count)
        logging.info(f"Successfully set vcpus to {core_count} for node: {node_name}")

    def get_ram_kib(self, node_name):
        xml = self._get_xml(node_name)
        memory_element = xml.getElementsByTagName('currentMemory')[0]
        return int(memory_element.firstChild.nodeValue)

    def set_ram_kib(self, node_name, ram_kib):
        logging.info(f"Going to set memory to {ram_kib} for node: {node_name}")
        xml = self._get_xml(node_name)
        memory_element = xml.getElementsByTagName('memory')[0]
        memory_element.firstChild.replaceWholeText(ram_kib)
        current_memory_element = xml.getElementsByTagName('currentMemory')[0]
        current_memory_element.firstChild.replaceWholeText(ram_kib)
        dom = self.libvirt_connection.defineXML(xml.toprettyxml())
        if dom is None:
            raise Exception(f"Failed to set memory for node: {node_name}")
        logging.info(f"Successfully set memory to {ram_kib} for node: {node_name}")

    def _get_xml(self, node_name):
        dom = self.libvirt_connection.lookupByName(node_name)
        current_xml = dom.XMLDesc(0)
        return minidom.parseString(current_xml.encode('utf-8'))
