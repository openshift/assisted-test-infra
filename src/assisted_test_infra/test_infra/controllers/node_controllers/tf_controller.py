from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from assisted_test_infra.test_infra import BaseClusterConfig
from assisted_test_infra.test_infra.controllers.node_controllers import Disk, Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from assisted_test_infra.test_infra.tools import terraform_utils
from assisted_test_infra.test_infra.utils import TerraformControllerUtil, utils


class TFController(NodeController, ABC):
    _entity_config: BaseClusterConfig

    def __init__(self, config: BaseNodesConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self._tf = None
        self._provider_client = None

    @property
    def tf(self):
        return self._tf

    def init_controller(self):
        folder = TerraformControllerUtil.create_folder(self.cluster_name, platform=self._config.tf_platform)
        self._tf = terraform_utils.TerraformUtils(working_dir=folder, terraform_init=False)

    @property
    def cluster_name(self):
        return self._entity_config.cluster_name.get()

    @abstractmethod
    def terraform_vm_resource_type(self) -> str:
        pass

    def _get_tf_resource(self, resource_type: str) -> List[Dict[str, Any]]:
        resource_object_type = self._tf.get_resources(resource_type=resource_type)

        if not resource_object_type:
            return list()

        return [instance for resource_objects in resource_object_type for instance in resource_objects["instances"]]

    def _get_tf_vms(self) -> List[Dict[str, Any]]:
        return self._get_tf_resource(self.terraform_vm_resource_type)

    def get_all_vars(self):
        return {**self._config.get_all(), **self._entity_config.get_all(), "cluster_name": self.cluster_name}

    @abstractmethod
    def _get_provider_client(self) -> object:
        pass

    def prepare_nodes(self):
        config = self.get_all_vars()
        self._provider_client = self._get_provider_client()
        self._tf.set_and_apply(**config)
        nodes = self.list_nodes()
        for node in nodes:
            self.set_boot_order(node.name)

        return nodes

    @property
    def terraform_vm_name_key(self) -> str:
        return "name"

    def _tf_vm_to_node(self, terraform_vm_state: Dict[str, Any]) -> Node:
        return Node(
            name=terraform_vm_state["attributes"][self.terraform_vm_name_key],
            private_ssh_key_path=self._config.private_ssh_key_path,
            node_controller=self,
        )

    def list_nodes(self) -> List[Node]:
        tf_vms = self._get_tf_vms()
        return list(map(self._tf_vm_to_node, tf_vms))

    def _get_vm(self, node_name: str) -> Optional[Dict[str, Any]]:
        return next(
            (vm for vm in self._get_tf_vms() if vm["attributes"][self.terraform_vm_name_key] == node_name), None
        )

    @abstractmethod
    def get_cpu_cores(self, node_name: str) -> int:
        pass

    @abstractmethod
    def get_ram_kib(self, node_name: str) -> int:
        pass

    @abstractmethod
    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        pass

    def destroy_all_nodes(self) -> None:
        self._tf.destroy(force=False)

    def start_all_nodes(self) -> List[Node]:
        nodes = self.list_nodes()

        for node in nodes:
            self.start_node(node.name, check_ips=False)

        return self.list_nodes()

    def shutdown_all_nodes(self) -> None:
        nodes = self.list_nodes()

        for node in nodes:
            self.shutdown_node(node.name)

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        utils.add_dns_record(
            cluster_name=self.cluster_name,
            base_dns_domain=self._entity_config.base_dns_domain,
            api_ip=api_ip,
            ingress_ip=ingress_ip,
        )

    def get_ingress_and_api_vips(self) -> dict[str, list[dict]] | None:
        if self._entity_config.api_vips and self._entity_config.ingress_vips:
            return {
                "api_vips": self._entity_config.api_vips,
                "ingress_vips": self._entity_config.ingress_vips,
            }

        return None

    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        pass

    def list_disks(self, node_name: str) -> List[Disk]:
        pass

    def format_all_node_disks(self) -> None:
        pass

    def list_networks(self) -> List[Any]:
        pass

    def list_leases(self, network_name: str) -> List[Any]:
        pass

    def attach_test_disk(self, node_name: str, disk_size: int, bus="scsi", bootable=False, persistent=False, with_wwn=False):
        pass

    def detach_all_test_disks(self, node_name: str):
        pass

    def get_cluster_network(self) -> str:
        pass

    def setup_time(self) -> str:
        pass

    def set_per_device_boot_order(self, node_name, key: Callable[[Disk], int]) -> None:
        pass

    def get_host_id(self, node_name: str) -> str:
        pass

    def set_cpu_cores(self, node_name: str, core_count: int) -> None:
        pass

    def set_ram_kib(self, node_name: str, ram_kib: int) -> None:
        pass

    def attach_interface(self, node_name, network_xml: str):
        pass

    def add_interface(self, node_name, network_name, target_interface: str) -> str:
        pass

    def undefine_interface(self, node_name: str, mac: str):
        pass

    def create_network(self, network_xml: str):
        pass

    def get_network_by_name(self, network_name: str):
        pass

    def destroy_network(self, network):
        pass

    def set_single_node_ip(self, ip):
        pass
