import ipaddress
import random
import subprocess
from typing import Any, Callable, Dict, List, Tuple, Union

from assisted_test_infra.test_infra import BaseClusterConfig
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config.base_aws_config import BaseAwsConfig
from assisted_test_infra.test_infra.tools import terraform_utils
from assisted_test_infra.test_infra.utils import TerraformControllerUtil, utils
from service_client import log


class AwsController(NodeController):
    _config: BaseAwsConfig

    def __init__(self, config: BaseAwsConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self.cluster_name = cluster_config.cluster_name.get()
        folder = TerraformControllerUtil.create_folder(self.cluster_name, platform=config.tf_platform)
        self._tf = terraform_utils.TerraformUtils(working_dir=folder, terraform_init=False)
        self._aws_client = None

    def prepare_nodes(self):
        config = {**self._config.get_all(), **self._entity_config.get_all(), "cluster_name": self.cluster_name}
        self._tf.set_and_apply(**config)

        return self.list_nodes()

    def _get_vm(self, node_name: str) -> Dict[str, Any]:
        return next((vm for vm in self._get_tf_vms() if vm["attributes"]["tags"]["Name"] == node_name), None)

    def _get_tf_vms(self) -> List[Dict[str, Any]]:
        vms_object_type = self._tf.get_resources(resource_type="aws_instance")

        if not vms_object_type:
            return list()

        return [vm_instance for vms_objects in vms_object_type for vm_instance in vms_objects["instances"]]

    def _aws_vm_to_node(self, terraform_vm_state: Dict[str, Any]) -> Node:
        return Node(
            name=terraform_vm_state["attributes"]["tags"]["Name"],
            private_ssh_key_path=None,
            node_controller=self,
        )

    def list_nodes(self) -> List[Node]:
        tf_vms = self._get_tf_vms()
        return list(map(self._aws_vm_to_node, tf_vms))

    def get_cpu_cores(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["cpu_core_count"]

    def get_ram_kib(self, node_name: str) -> int:
        return 16 * 10**9

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        ips = [self._get_vm(node_name)["attributes"]["private_ip"]]
        return ips, ["DE:AD:BE:EF:DE:AD"]

    def destroy_all_nodes(self) -> None:
        self._tf.destroy(force=False)

    def start_node(self, node_name: str, check_ips: bool) -> None:
        pass

    def start_all_nodes(self) -> List[Node]:
        raise NotImplementedError

    def shutdown_node(self, node_name: str) -> None:
        raise NotImplementedError

    def shutdown_all_nodes(self) -> None:
        raise NotImplementedError

    def restart_node(self, node_name: str) -> None:
        raise NotImplementedError

    def get_ingress_and_api_vips(self):
        return None

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        pass

    def set_boot_order(self, node_name, cd_first=False) -> None:
        raise NotImplementedError

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
        return "irrelevant"

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

    def set_ipxe_url(self, network_name: str, ipxe_url: str):
        self._config.ipxe_script = f"#!ipxe\n\ndhcp\nchain {ipxe_url}"
