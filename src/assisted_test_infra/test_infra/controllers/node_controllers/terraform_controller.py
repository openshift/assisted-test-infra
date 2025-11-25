import json
import os
import shutil
import warnings
from ipaddress import ip_address, ip_network
from typing import Dict, List, Union

from munch import Munch
from netaddr import IPNetwork

import consts
import virsh_cleanup
from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, BaseTerraformConfig, utils
from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.tools import static_network, terraform_utils
from assisted_test_infra.test_infra.utils import TerraformControllerUtil
from assisted_test_infra.test_infra.utils.base_name import BaseName, get_name_suffix
from consts import resources
from service_client import log


class TerraformController(LibvirtController):
    def __init__(self, config: BaseTerraformConfig, entity_config: Union[BaseClusterConfig, BaseInfraEnvConfig]):
        super().__init__(config, entity_config, libvirt_uri=config.libvirt_uri)
        self._entity_name = self._entity_config.entity_name
        self._suffix = self._entity_name.suffix or get_name_suffix()
        self.tf_folder = config.tf_folder or self._create_tf_folder(self._entity_name.get(), config.tf_platform)
        self.network_name = config.network_name + self._suffix
        self.tf = terraform_utils.TerraformUtils(working_dir=self.tf_folder)
        self.master_ips = None
        self._params = Munch()

    @property
    def entity_name(self) -> BaseName:
        return self._entity_name

    @property
    def cluster_name(self) -> str:
        warnings.warn("cluster_name is deprecated. Use Controller.entity_name instead.", DeprecationWarning)
        return self._entity_name.get()

    def _get_primary_stack(self) -> str:
        """Get the primary stack configuration from entity_config (cluster config), defaulting to 'ipv4'"""
        if self._entity_config:
            return getattr(self._entity_config, "primary_stack", "ipv4")
        return getattr(self._config, "primary_stack", "ipv4")

    def get_all_vars(self):
        cluster_name = self._entity_config.entity_name.get()
        return {**self._config.get_all(), **self._entity_config.get_all(), "cluster_name": cluster_name}

    def _get_params_from_config(self) -> Munch:
        return self._terraform_params(**self._config.get_all())

    def _create_tf_folder(self, name: str, platform: str):
        if isinstance(self._entity_config, BaseInfraEnvConfig):
            return TerraformControllerUtil.create_folder(name, "baremetal_infra_env")

        return TerraformControllerUtil.create_folder(name, platform)

    def _get_disk_encryption_appliance(self):
        if isinstance(self._entity_config, BaseInfraEnvConfig):
            log.debug("Infra-env is not associated with any disk-encryption configuration")
            return {}

        assert (
            self._entity_config.disk_encryption_mode in consts.DiskEncryptionMode.all()
        ), f"{self._entity_config.disk_encryption_mode} is not a supported disk encryption mode"

        master_vtpm2 = worker_vtpm2 = arbiter_vtpm2 = False

        if self._entity_config.disk_encryption_mode == consts.DiskEncryptionMode.TPM_VERSION_2:
            if self._entity_config.disk_encryption_roles == consts.DiskEncryptionRoles.ALL:
                master_vtpm2 = worker_vtpm2 = arbiter_vtpm2 = True
            if consts.DiskEncryptionRoles.MASTERS in self._entity_config.disk_encryption_roles:
                master_vtpm2 = True
            if consts.DiskEncryptionRoles.WORKERS in self._entity_config.disk_encryption_roles:
                worker_vtpm2 = True
            if consts.DiskEncryptionRoles.ARBITERS in self._entity_config.disk_encryption_roles:
                arbiter_vtpm2 = True

        return {"master_vtpm2": master_vtpm2, "worker_vtpm2": worker_vtpm2, "arbiter_vtpm2": arbiter_vtpm2}

    # TODO move all those to conftest and pass it as kwargs
    # TODO-2 Remove all parameters defaults after moving to new workflow and use config object instead
    def _terraform_params(self, **kwargs) -> Munch:
        master_boot_devices = self._config.master_boot_devices
        worker_boot_devices = self._config.worker_boot_devices
        arbiter_boot_devices = self._config.arbiter_boot_devices
        params = {
            "libvirt_worker_memory": kwargs.get("worker_memory"),
            "libvirt_arbiter_memory": kwargs.get("arbiter_memory", resources.DEFAULT_ARBITER_MEMORY),
            "libvirt_master_memory": kwargs.get("master_memory", resources.DEFAULT_MASTER_MEMORY),
            "libvirt_worker_vcpu": kwargs.get("worker_vcpu", resources.DEFAULT_MASTER_CPU),
            "libvirt_arbiter_vcpu": kwargs.get("arbiter_vcpu", resources.DEFAULT_ARBITER_CPU),
            "libvirt_master_vcpu": kwargs.get("master_vcpu", resources.DEFAULT_MASTER_CPU),
            "worker_count": kwargs.get("workers_count", 0),
            "arbiter_count": kwargs.get("arbiters_count", 0),
            "master_count": kwargs.get("masters_count", consts.NUMBER_OF_MASTERS),
            "machine_cidr": self.get_primary_machine_cidr(),
            "libvirt_network_name": self.network_name,
            "libvirt_network_mtu": kwargs.get("network_mtu", 1500),
            "libvirt_dns_records": kwargs.get("dns_records", {}),
            # TODO change to namespace index
            "libvirt_network_if": self._config.net_asset.libvirt_network_if,
            "libvirt_worker_disk": kwargs.get("worker_disk", resources.DEFAULT_WORKER_DISK),
            "libvirt_arbiter_disk": kwargs.get("arbiter_disk", resources.DEFAULT_ARBITER_DISK),
            "libvirt_master_disk": kwargs.get("master_disk", resources.DEFAULT_MASTER_DISK),
            "libvirt_secondary_network_name": consts.TEST_SECONDARY_NETWORK + self._suffix,
            "libvirt_storage_pool_path": kwargs.get("storage_pool_path", os.path.join(os.getcwd(), "storage_pool")),
            # TODO change to namespace index
            "libvirt_secondary_network_if": self._config.net_asset.libvirt_secondary_network_if,
            "enable_dhcp": (False if kwargs.get("is_static_ip") else True),
            "provisioning_cidr": self._config.net_asset.provisioning_cidr,
            "running": self._config.running,
            "single_node_ip": kwargs.get("single_node_ip", ""),
            "master_disk_count": kwargs.get("master_disk_count", resources.DEFAULT_DISK_COUNT),
            "worker_disk_count": kwargs.get("worker_disk_count", resources.DEFAULT_DISK_COUNT),
            "arbiter_disk_count": kwargs.get("arbiter_disk_count", resources.DEFAULT_DISK_COUNT),
            "worker_cpu_mode": kwargs.get("worker_cpu_mode", consts.WORKER_TF_CPU_MODE),
            "arbiter_cpu_mode": kwargs.get("arbiter_cpu_mode", consts.ARBITER_TF_CPU_MODE),
            "master_cpu_mode": kwargs.get("master_cpu_mode", consts.MASTER_TF_CPU_MODE),
            "master_boot_devices": (
                master_boot_devices if master_boot_devices is not None else consts.DEFAULT_BOOT_DEVICES
            ),
            "worker_boot_devices": (
                worker_boot_devices if worker_boot_devices is not None else consts.DEFAULT_BOOT_DEVICES
            ),
            "arbiter_boot_devices": (
                arbiter_boot_devices if arbiter_boot_devices is not None else consts.DEFAULT_BOOT_DEVICES
            ),
            **self._get_disk_encryption_appliance(),
        }

        params.update(self._get_specific_tf_entity_params())
        for key in [
            "libvirt_master_ips",
            "libvirt_secondary_master_ips",
            "libvirt_worker_ips",
            "libvirt_secondary_worker_ips",
            "libvirt_arbiter_ips",
            "libvirt_secondary_arbiter_ips",
        ]:
            value = kwargs.get(key)
            if value is not None:
                params[key] = value
        return Munch.fromDict(params)

    def _get_specific_tf_entity_params(self) -> Dict[str, str]:
        if isinstance(self._entity_config, BaseClusterConfig):
            return {"cluster_name": self.entity_name.get(), "cluster_domain": self._entity_config.base_dns_domain}
        elif isinstance(self._entity_config, BaseInfraEnvConfig):
            return {"infra_env_name": self._entity_name.get()}

        return dict()

    def list_nodes(self) -> List[Node]:
        return self.list_nodes_with_name_filter(self._entity_name.get())

    def generate_macs(self, nodes_count: int) -> List[str]:
        num_to_create = (
            nodes_count * self._entity_config.num_bonded_slaves if self._entity_config.is_bonded else nodes_count
        )
        return static_network.generate_macs(num_to_create)

    # Run make run terraform -> creates vms
    def _create_nodes(self, running=True):
        log.info("Creating tfvars")
        self._params = self._get_params_from_config()

        self._fill_tfvars(running)
        log.info("Start running terraform")
        self.tf.apply()
        if self._config.static_ips_vlan:
            self._ensure_vlan_interface()
        if self._params.running:
            self.wait_till_nodes_are_ready(network_name=self._params.libvirt_network_name)

    def _get_vips(self):
        vips = self.get_ingress_and_api_vips()
        if self._config.api_vips:
            api_vips = [i.ip for i in self._config.api_vips]
        else:
            api_vips = [i.get("ip") for i in vips["api_vips"]]

        if self._config.ingress_vips:
            ingress_vips = [i.ip for i in self._config.ingress_vips]
        else:
            ingress_vips = [i.get("ip") for i in vips["ingress_vips"]]

        return api_vips, ingress_vips

    # Filling tfvars json files with terraform needed variables to spawn vms
    def _fill_tfvars(self, running=True):
        log.info("Filling tfvars")

        tfvars = dict()
        machine_cidr = self.get_primary_machine_cidr()

        tfvars["libvirt_uri"] = self.libvirt_uri
        tfvars["master_count"] = self._params.master_count
        log.info("Machine cidr is: %s", machine_cidr)
        master_starting_ip = str(ip_address(ip_network(machine_cidr).network_address) + 10)
        worker_starting_ip = str(ip_address(ip_network(machine_cidr).network_address) + 10 + tfvars["master_count"])
        arbiter_starting_ip = str(
            ip_address(ip_network(machine_cidr).network_address)
            + 10
            + tfvars["master_count"]
            + self._params.worker_count
        )
        tfvars["image_path"] = self._entity_config.iso_download_path
        tfvars["worker_image_path"] = self._entity_config.worker_iso_download_path or tfvars["image_path"]
        self.master_ips = tfvars["libvirt_master_ips"] = self._create_address_list(
            self._params.master_count, starting_ip_addr=master_starting_ip
        )
        tfvars["libvirt_worker_ips"] = self._create_address_list(
            self._params.worker_count, starting_ip_addr=worker_starting_ip
        )
        tfvars["libvirt_arbiter_ips"] = self._create_address_list(
            self._params.arbiter_count, starting_ip_addr=arbiter_starting_ip
        )
        if self._config.ingress_dns:
            for service in ["console-openshift-console", "canary-openshift-ingress", "oauth-openshift"]:
                self._params["libvirt_dns_records"][
                    ".".join([service, "apps", self._config.cluster_name, self._entity_config.base_dns_domain])
                ] = tfvars["libvirt_worker_ips"][0][0]
        tfvars["machine_cidr_addresses"] = self.get_all_machine_addresses()
        tfvars["provisioning_cidr_addresses"] = self.get_all_provisioning_addresses()
        tfvars["bootstrap_in_place"] = self._config.bootstrap_in_place
        tfvars["api_vips"], tfvars["ingress_vips"] = self._get_vips()

        if self._config.base_cluster_domain:
            tfvars["base_cluster_domain"] = self._config.base_cluster_domain

        tfvars["running"] = running
        tfvars["libvirt_master_macs"] = self.generate_macs(self._params.master_count)
        tfvars["libvirt_worker_macs"] = self.generate_macs(self._params.worker_count)
        tfvars["libvirt_arbiter_macs"] = self.generate_macs(self._params.arbiter_count)
        tfvars["master_boot_devices"] = self._params.master_boot_devices
        tfvars["worker_boot_devices"] = self._params.worker_boot_devices
        tfvars["arbiter_boot_devices"] = self._params.arbiter_boot_devices
        tfvars["load_balancer_type"] = self._entity_config.load_balancer_type
        if self._entity_config.is_bonded:
            tfvars["slave_interfaces"] = True
            tfvars["network_interfaces_count"] = self._entity_config.num_bonded_slaves
        tfvars.update(self._params)
        tfvars.update(self._secondary_tfvars())

        with open(os.path.join(self.tf_folder, consts.TFVARS_JSON_NAME), "w") as _file:
            json.dump(tfvars, _file)

    def _secondary_tfvars(self):
        provisioning_cidr = self.get_provisioning_cidr()
        secondary_master_starting_ip = str(ip_address(ip_network(provisioning_cidr).network_address) + 10)
        secondary_worker_starting_ip = str(
            ip_address(ip_network(provisioning_cidr).network_address) + 10 + int(self._params.master_count)
        )
        secondary_arbiter_starting_ip = str(
            ip_address(ip_network(provisioning_cidr).network_address)
            + 10
            + int(self._params.master_count)
            + int(self._params.worker_count)
        )
        return {
            "libvirt_secondary_worker_ips": self._create_address_list(
                self._params.worker_count, starting_ip_addr=secondary_worker_starting_ip
            ),
            "libvirt_secondary_master_ips": self._create_address_list(
                self._params.master_count, starting_ip_addr=secondary_master_starting_ip
            ),
            "libvirt_secondary_arbiter_ips": self._create_address_list(
                self._params.arbiter_count, starting_ip_addr=secondary_arbiter_starting_ip
            ),
            "libvirt_secondary_master_macs": self.generate_macs(self._params.master_count),
            "libvirt_secondary_worker_macs": self.generate_macs(self._params.worker_count),
            "libvirt_secondary_arbiter_macs": self.generate_macs(self._params.arbiter_count),
        }

    def start_all_nodes(self):
        nodes = self.list_nodes()

        if len(nodes) == 0:
            self._create_nodes()
            return self.list_nodes()
        else:
            return super().start_all_nodes()

    def format_node_disk(self, node_name: str, disk_index: int = 0):
        log.info("Formatting disk for %s", node_name)
        self.format_disk(f"{self._params.libvirt_storage_pool_path}/{self.entity_name}/{node_name}-disk-{disk_index}")

    def get_ingress_and_api_vips(self) -> Dict[str, List[dict]]:
        """Pick IPs for setting static access endpoint IPs.

        Using <subnet>.100 for the API endpoint and <subnet>.101 for the ingress endpoint
        (the IPv6 values are appropriately <sub-net>:64 and <sub-net>:65).

        For dual-stack clusters, returns both IPv4 and IPv6 VIPs, ordered by PRIMARY_STACK.

        This method is not applicable for SNO clusters, where access IPs should be the node's IP.
        """
        api_vips = []
        ingress_vips = []
        primary_stack = self._get_primary_stack()

        # For dual-stack, get VIPs from both networks
        if self.is_ipv4 and self.is_ipv6:
            ipv4_network = ip_network(self._config.net_asset.machine_cidr)
            ipv4_starting_ip = ip_address(ipv4_network.network_address)
            ipv4_ips = utils.create_ip_address_list(2, starting_ip_addr=ipv4_starting_ip + 100)

            ipv6_network = ip_network(self._config.net_asset.machine_cidr6)
            ipv6_starting_ip = ip_address(ipv6_network.network_address)
            ipv6_ips = utils.create_ip_address_list(2, starting_ip_addr=ipv6_starting_ip + 100)

            # Order based on PRIMARY_STACK
            if primary_stack == "ipv6":
                # IPv6-primary: IPv6 first, then IPv4
                api_vips = [{"ip": ipv6_ips[0]}, {"ip": ipv4_ips[0]}]
                ingress_vips = [{"ip": ipv6_ips[1]}, {"ip": ipv4_ips[1]}]
            else:
                # IPv4-primary: IPv4 first, then IPv6
                api_vips = [{"ip": ipv4_ips[0]}, {"ip": ipv6_ips[0]}]
                ingress_vips = [{"ip": ipv4_ips[1]}, {"ip": ipv6_ips[1]}]
        else:
            # Single-stack: use primary network only
            network_subnet_starting_ip = ip_address(ip_network(self.get_primary_machine_cidr()).network_address)
            ips = utils.create_ip_address_list(2, starting_ip_addr=network_subnet_starting_ip + 100)
            api_vips = [{"ip": ips[0]}]
            ingress_vips = [{"ip": ips[1]}]

        return {"api_vips": api_vips, "ingress_vips": ingress_vips}

    @utils.on_exception(message="Failed to run terraform delete", silent=True)
    def _create_address_list(self, num, starting_ip_addr):
        # IPv6 addresses can't be set alongside mac addresses using TF libvirt provider
        # Otherwise results: "Invalid to specify MAC address '<mac>' in network '<network>' IPv6 static host definition"
        # see https://github.com/dmacvicar/terraform-provider-libvirt/issues/396
        if self.is_ipv6:
            return utils.create_empty_nested_list(num)
        return utils.create_ip_address_nested_list(num, starting_ip_addr=starting_ip_addr)

    def get_primary_machine_cidr(self):
        """Get the primary machine CIDR based on primary_stack setting"""
        primary_stack = self._get_primary_stack()

        if primary_stack == "ipv6" and self.is_ipv4 and self.is_ipv6:
            # IPv6-primary dual-stack
            return self._config.net_asset.machine_cidr6
        elif self.is_ipv6 and not self.is_ipv4:
            # IPv6-only
            return self._config.net_asset.machine_cidr6
        else:
            # IPv4-primary or IPv4-only
            return self._config.net_asset.machine_cidr

    def get_provisioning_cidr(self):
        """Get the provisioning CIDR based on primary_stack setting"""
        primary_stack = self._get_primary_stack()

        if primary_stack == "ipv6" and self.is_ipv4 and self.is_ipv6:
            # IPv6-primary dual-stack
            return self._config.net_asset.provisioning_cidr6
        elif self.is_ipv6 and not self.is_ipv4:
            # IPv6-only
            return self._config.net_asset.provisioning_cidr6
        else:
            # IPv4-primary or IPv4-only
            return self._config.net_asset.provisioning_cidr

    def get_all_machine_addresses(self) -> List[str]:
        """Get all subnets that belong to the primary NIC."""
        addresses = []
        primary_stack = self._get_primary_stack()
        log.debug(f"primary_stack: {primary_stack}")

        if primary_stack == "ipv6" and self.is_ipv4 and self.is_ipv6:
            # IPv6-primary dual-stack
            if self.is_ipv6:
                addresses.append(self._config.net_asset.machine_cidr6)  # IPv6 first
            if self.is_ipv4:
                addresses.append(self._config.net_asset.machine_cidr)  # IPv4 second
        else:
            # IPv4-primary dual-stack (default)
            if self.is_ipv4:
                addresses.append(self._config.net_asset.machine_cidr)  # IPv4 first
            if self.is_ipv6:
                addresses.append(self._config.net_asset.machine_cidr6)  # IPv6 second

        return addresses

    def get_all_provisioning_addresses(self) -> List[str]:
        """Get all subnets that belong to the secondary NIC."""
        addresses = []

        if self.is_ipv4:
            addresses.append(self._config.net_asset.provisioning_cidr)

        if self.is_ipv6:
            addresses.append(self._config.net_asset.provisioning_cidr6)

        return addresses

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        utils.add_dns_record(
            cluster_name=self._entity_name,
            base_dns_domain=self._entity_config.base_dns_domain,
            api_ip=api_ip,
            ingress_ip=ingress_ip,
        )

    def set_dns_for_user_managed_network(self) -> None:
        machine_cidr = self.get_primary_machine_cidr()
        nameserver_ip = str(IPNetwork(machine_cidr).ip + 1)
        self.set_dns(nameserver_ip, nameserver_ip)

    def _try_to_delete_nodes(self):
        log.info("Start running terraform delete")
        self.tf.destroy(force=False)

    def destroy_all_nodes(self, delete_tf_folder=False):
        """Runs terraform destroy and then cleans it with virsh cleanup to delete
        everything relevant.
        """

        log.info("Deleting all nodes")
        self._params = self._get_params_from_config()

        if getattr(self._config, "static_ips_vlan", False):
            try:
                self._delete_vlan_interface()
            except Exception:
                log.exception("Failed deleting VLAN sub-interface on host")

        if os.path.exists(self.tf_folder):
            self._try_to_delete_nodes()

        self._delete_virsh_resources(
            self._entity_name.get(), self._params.libvirt_network_name, self._params.libvirt_secondary_network_name
        )
        tfstate_path = f"{self.tf_folder}/{consts.TFSTATE_FILE}"
        if os.path.exists(tfstate_path):
            log.info(f"Deleting tf state file: {tfstate_path}")
            os.remove(tfstate_path)

        if delete_tf_folder:
            log.info("Deleting %s", self.tf_folder)
            shutil.rmtree(self.tf_folder)

    @classmethod
    def _delete_virsh_resources(cls, *filters):
        log.info("Deleting virsh resources (filters: %s)", filters)
        skip_list = virsh_cleanup.DEFAULT_SKIP_LIST
        skip_list.extend(["minikube", "minikube-net"])
        virsh_cleanup.clean_virsh_resources(skip_list=skip_list, resource_filter=filters)

    def prepare_nodes(self):
        log.info("Preparing nodes")
        if not os.path.exists(self._entity_config.iso_download_path):
            utils.recreate_folder(os.path.dirname(self._entity_config.iso_download_path), force_recreate=False)
            # if file not exist lets create dummy
            utils.touch(self._entity_config.iso_download_path)

        self._config.running = False
        self._create_nodes()

    def get_cluster_network(self):
        log.info(f"Cluster network name: {self.network_name}")
        return self.network_name

    def set_single_node_ip(self, ip):
        self.tf.change_variables({"single_node_ip": ip})

    def get_day2_static_network_data(self):
        return static_network.generate_day2_static_network_data_from_tf(self.tf_folder, self._config.workers_count)

    def wait_till_nodes_are_ready(self, network_name: str = None):
        return super().wait_till_nodes_are_ready(network_name or self.network_name)

    def _get_vlan_iface_name(self) -> str:
        bridge = self._config.net_asset.libvirt_network_if
        vlan_id = getattr(self._config, "vlan_id", 100) or 100
        return f"{bridge}.{vlan_id}"

    def _get_ip_addrs_for_iface(self, iface: str, family_flag: str) -> list[str]:
        """
        Return CIDR strings for addresses on iface.
        family_flag: '-4' or '-6'
        """
        out, _, _ = utils.run_command(f"ip -o {family_flag} addr show dev {iface}", raise_errors=False)
        cidrs: list[str] = []
        if not out:
            return cidrs
        for line in out.splitlines():
            parts = line.split()
            # Expected: <idx>: <name> inet|inet6 <addr>/<prefix> ...
            if len(parts) >= 4 and parts[2] in ("inet", "inet6"):
                addr = parts[3]
                # Skip IPv6 link-local
                if parts[2] == "inet6" and addr.lower().startswith("fe80:"):
                    continue
                cidrs.append(addr)
        return cidrs

    def _iface_has_addr(self, iface: str, cidr: str) -> bool:
        family_flag = "-6" if ":" in cidr else "-4"
        out, _, _ = utils.run_command(f"ip -o {family_flag} addr show dev {iface}", raise_errors=False)
        if not out:
            return False
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[3] == cidr:
                return True
        return False

    def _move_bridge_addresses_to_vlan(self, bridge: str, vlan_iface: str) -> None:
        """Move all non-link-local IPv4/IPv6 addresses from bridge to vlan_iface."""
        ipv4_cidrs = self._get_ip_addrs_for_iface(bridge, "-4")
        ipv6_cidrs = self._get_ip_addrs_for_iface(bridge, "-6")

        for cidr in ipv4_cidrs + ipv6_cidrs:
            try:
                if not self._iface_has_addr(vlan_iface, cidr):
                    utils.run_command(f"ip addr add {cidr} dev {vlan_iface}")
                utils.run_command(f"ip addr del {cidr} dev {bridge}")
                log.info("Moved %s from %s to %s", cidr, bridge, vlan_iface)
            except Exception:
                log.exception("Failed moving address %s from %s to %s", cidr, bridge, vlan_iface)

    def _ensure_vlan_interface(self) -> None:
        vlan_iface = self._get_vlan_iface_name()
        bridge = self._config.net_asset.libvirt_network_if
        vlan_id = getattr(self._config, "vlan_id", 100) or 100

        # Check if VLAN iface exists
        _, _, rc = utils.run_command(f"ip link show dev {vlan_iface}", raise_errors=False)
        if rc == 0:
            log.info("VLAN interface %s already exists", vlan_iface)
        else:
            log.info("Creating VLAN interface %s on bridge %s (id %s)", vlan_iface, bridge, vlan_id)
            utils.run_command(f"ip link add link {bridge} name {vlan_iface} type vlan id {vlan_id}")
        # Bring VLAN iface up (idempotent)
        utils.run_command(f"ip link set dev {vlan_iface} up")
        # Move any IP addresses from bridge to VLAN iface
        self._move_bridge_addresses_to_vlan(bridge, vlan_iface)

    def _delete_vlan_interface(self) -> None:
        vlan_iface = self._get_vlan_iface_name()
        # Delete if exists
        _, _, rc = utils.run_command(f"ip link show dev {vlan_iface}", raise_errors=False)
        if rc == 0:
            log.info("Deleting VLAN interface %s", vlan_iface)
            utils.run_command(f"sudo ip link del dev {vlan_iface}")
        else:
            log.info("VLAN interface %s not present; nothing to delete", vlan_iface)
