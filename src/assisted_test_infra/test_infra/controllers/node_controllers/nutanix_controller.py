import ipaddress
import random
import subprocess
from typing import Any, Callable, Dict, List, Tuple, Union

from nutanix_api import NutanixApiClient, NutanixCluster, NutanixSubnet, NutanixVM
from nutanix_api.nutanix_vm import PowerState, VMBootDevices

from assisted_test_infra.test_infra import BaseClusterConfig
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config.base_nutanix_config import BaseNutanixConfig
from assisted_test_infra.test_infra.tools import terraform_utils
from assisted_test_infra.test_infra.utils import TerraformControllerUtil, utils
from service_client import log


class NutanixController(NodeController):
    _config: BaseNutanixConfig

    def __init__(self, config: BaseNutanixConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self.cluster_name = cluster_config.cluster_name.get()
        folder = TerraformControllerUtil.create_folder(self.cluster_name, platform=config.tf_platform)
        self.tf = terraform_utils.TerraformUtils(working_dir=folder, terraform_init=False)
        self._nutanix_client = None

    def get_all_vars(self):
        return {**self._config.get_all(), **self._entity_config.get_all(), "cluster_name": self.cluster_name}

    def prepare_nodes(self):
        config = self.get_all_vars()
        self._nutanix_client = self._create_nutanix_client()
        self.tf.set_and_apply(**config)
        nodes = self.list_nodes()
        for node in nodes:
            self.set_boot_order(node.name)

        return nodes

    def _get_nutanix_vm(self, tf_vm_name: str) -> Union[NutanixVM, None]:
        nutanix_vms = NutanixVM.list_entities(self._nutanix_client)
        _, macs = self.get_node_ips_and_macs(tf_vm_name)

        for vm in nutanix_vms:
            for mac in vm.mac_addresses:
                if mac in macs:
                    return vm

        raise ValueError(f"Can't find node with name: {tf_vm_name}")

    def _nutanix_vm_to_node(self, terraform_vm_state: Dict[str, Any]) -> Node:
        return Node(
            name=terraform_vm_state["attributes"]["name"],
            private_ssh_key_path=self._config.private_ssh_key_path,
            node_controller=self,
        )

    def list_nodes(self) -> List[Node]:
        tf_vms = self._get_tf_vms()
        return list(map(self._nutanix_vm_to_node, tf_vms))

    def get_cpu_cores(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["num_sockets"]

    def get_ram_kib(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["memory_size_mib"] * 1024

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        vm_attributes = self._get_vm(node_name)["attributes"]
        ips = []
        macs = []

        for nic in vm_attributes["nic_list"]:
            for ips_list in nic["ip_endpoint_list"]:
                ips.append(ips_list["ip"])

            macs.append(nic["mac_address"])

        return ips, macs

    def destroy_all_nodes(self) -> None:
        self.tf.destroy(force=False)

    def start_node(self, node_name: str, check_ips: bool) -> None:
        """
        :raises ValueError if node_name does not exist
        """
        vm = self._get_nutanix_vm(node_name)
        if vm.power_state != PowerState.ON.value:
            log.info(f"Powering on nutanix node {node_name}")
            vm.power_on()
        else:
            log.warning(
                f"Attempted to power on node {node_name}, "
                f"but the vm is already on - vm.power_state={vm.power_state}"
            )

    def start_all_nodes(self) -> List[Node]:
        nodes = self.list_nodes()

        for node in nodes:
            self.start_node(node.name, check_ips=False)

        return self.list_nodes()

    def shutdown_node(self, node_name: str) -> None:
        vm = self._get_nutanix_vm(node_name)
        if vm.power_state != PowerState.OFF.value:
            log.info(f"Powering off nutanix node {node_name}")
            vm.power_on()
        else:
            log.warning(
                f"Attempted to power off node {node_name}, "
                f"but the vm is already off - vm.power_state={vm.power_state}"
            )

    def shutdown_all_nodes(self) -> None:
        nodes = self.list_nodes()

        for node in nodes:
            self.shutdown_node(node.name)

    def restart_node(self, node_name: str) -> None:
        vm = self._get_nutanix_vm(tf_vm_name=node_name)
        vm.power_off()
        vm.power_on()

    def get_ingress_and_api_vips(self):
        if not self._entity_config.vip_dhcp_allocation:
            if not self._entity_config.api_vip:
                raise ValueError("API VIP is not set")
            if not self._entity_config.ingress_vip:
                raise ValueError("Ingress VIP is not set")
            return {"api_vip": self._entity_config.api_vip, "ingress_vip": self._entity_config.ingress_vip}

        nutanix_subnet = next(
            s for s in NutanixSubnet.list_entities(self._nutanix_client) if s.name == self._config.nutanix_subnet
        )

        free_ips = set()
        max_ping_attempts = 30
        ip_network = ipaddress.ip_network(f"{nutanix_subnet.subnet_ip}/{nutanix_subnet.prefix_length}").network_address
        attempts = 1

        log.info("Attempting to find API and Ingress VIPs...")
        while len(free_ips) < 2 and attempts < max_ping_attempts:
            attempts += 1
            address = str(ipaddress.ip_address(ip_network) + random.randint(1, 160))

            log.debug(f"Sending ping to {address} (attempt {attempts})")

            try:
                subprocess.check_output("ping -c 1 " + address, shell=True, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                free_ips.add(address)

        if len(free_ips) != 2:
            raise ConnectionError("Failed to locate free API and Ingress VIPs")

        log.info(f"Found 2 optional VIPs: {free_ips}")
        return {"api_vip": free_ips.pop(), "ingress_vip": free_ips.pop()}

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        utils.add_dns_record(
            cluster_name=self.cluster_name,
            base_dns_domain=self._entity_config.base_dns_domain,
            api_ip=api_ip,
            ingress_ip=ingress_ip,
        )

    def set_boot_order(self, node_name, cd_first=False) -> None:
        vm = self._get_nutanix_vm(tf_vm_name=node_name)
        if cd_first:
            vm.update_boot_order(VMBootDevices.default_boot_order())
        else:
            vm.update_boot_order([VMBootDevices.DISK, VMBootDevices.CDROM, VMBootDevices.NETWORK])

    def _get_vm(self, node_name: str) -> Dict[str, Any]:
        return next((vm for vm in self._get_tf_vms() if vm["attributes"]["name"] == node_name), None)

    def _get_tf_vms(self) -> List[Dict[str, Any]]:
        vms_object_type = self.tf.get_resources(resource_type="nutanix_virtual_machine")

        if not vms_object_type:
            return list()

        return [vm_instance for vms_objects in vms_object_type for vm_instance in vms_objects["instances"]]

    def _create_nutanix_client(self) -> NutanixApiClient:
        nutanix_client = NutanixApiClient(
            self._config.nutanix_username,
            self._config.nutanix_password,
            self._config.nutanix_port,
            self._config.nutanix_endpoint,
        )

        for c in NutanixCluster.list_entities(nutanix_client):
            if c.name == self._config.nutanix_cluster:
                break
        else:
            raise ValueError(f"Unable to locate nutanix cluster - {self._config.nutanix_cluster}")

        return nutanix_client

    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        raise NotImplementedError

    def list_disks(self, node_name: str) -> List[Disk]:
        raise NotImplementedError

    def is_active(self, node_name) -> bool:
        raise NotImplementedError

    def format_all_node_disks(self) -> None:
        raise NotImplementedError

    def list_networks(self) -> List[Any]:
        raise NotImplementedError

    def list_leases(self, network_name: str) -> List[Any]:
        raise NotImplementedError

    def attach_test_disk(self, node_name: str, disk_size: int, bootable=False, persistent=False, with_wwn=False):
        raise NotImplementedError

    def detach_all_test_disks(self, node_name: str):
        raise NotImplementedError

    def get_cluster_network(self) -> str:
        raise NotImplementedError

    def setup_time(self) -> str:
        raise NotImplementedError

    def set_per_device_boot_order(self, node_name, key: Callable[[Disk], int]) -> None:
        raise NotImplementedError

    def get_host_id(self, node_name: str) -> str:
        raise NotImplementedError

    def set_cpu_cores(self, node_name: str, core_count: int) -> None:
        raise NotImplementedError

    def set_ram_kib(self, node_name: str, ram_kib: int) -> None:
        raise NotImplementedError

    def attach_interface(self, node_name, network_xml: str):
        raise NotImplementedError

    def add_interface(self, node_name, network_name, target_interface: str) -> str:
        raise NotImplementedError

    def undefine_interface(self, node_name: str, mac: str):
        raise NotImplementedError

    def create_network(self, network_xml: str):
        raise NotImplementedError

    def get_network_by_name(self, network_name: str):
        raise NotImplementedError

    def destroy_network(self, network):
        raise NotImplementedError

    def set_single_node_ip(self, ip):
        raise NotImplementedError
