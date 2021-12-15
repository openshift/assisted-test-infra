from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, SupportsAbs, Tuple, TypeVar

import libvirt
from test_infra.controllers.node_controllers.disk import Disk
from test_infra.controllers.node_controllers.node import Node
from test_infra.helper_classes.config import BaseEntityConfig
from test_infra.helper_classes.config.controller_config import BaseNodeConfig
from test_infra.utils import log


class NodeController(ABC):

    T = TypeVar("T", bound=SupportsAbs[BaseNodeConfig])

    def __init__(self, config: T, entity_config: BaseEntityConfig):
        self._config = config
        self._entity_config = entity_config

    def log_configuration(self):
        log.info(f"controller configuration={self._config}")

    @property
    def workers_count(self):
        return self._config.workers_count

    @property
    def masters_count(self):
        return self._config.masters_count

    @property
    def is_ipv4(self):
        return self._config.is_ipv4

    @property
    def is_ipv6(self):
        return self._config.is_ipv6

    @abstractmethod
    def list_nodes(self) -> List[Node]:
        pass

    @abstractmethod
    def list_disks(self, node_name: str) -> List[Disk]:
        pass

    @abstractmethod
    def list_networks(self) -> List[Any]:
        pass

    @abstractmethod
    def list_leases(self, network_name: str) -> List[Any]:
        pass

    @abstractmethod
    def shutdown_node(self, node_name: str) -> None:
        pass

    @abstractmethod
    def shutdown_all_nodes(self) -> None:
        pass

    @abstractmethod
    def start_node(self, node_name: str, check_ips: bool) -> None:
        pass

    @abstractmethod
    def start_all_nodes(self) -> List[Node]:
        pass

    @abstractmethod
    def restart_node(self, node_name: str) -> None:
        pass

    @abstractmethod
    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        pass

    @abstractmethod
    def format_all_node_disks(self) -> None:
        pass

    @abstractmethod
    def attach_test_disk(self, node_name: str, disk_size: int, bootable=False, persistent=False, with_wwn=False):
        """
        Attaches a test disk. That disk can later be detached with `detach_all_test_disks`
        :param with_wwn: Weather the disk should have a WWN(World Wide Name), Having a WWN creates a disk by-id link
        :param node_name: Node to attach disk to
        :param disk_size: Size of disk to attach
        :param bootable: Whether to format an MBR sector at the beginning of the disk
        :param persistent: Whether the disk should survive shutdowns
        """
        pass

    @abstractmethod
    def detach_all_test_disks(self, node_name: str):
        """
        Detaches all test disks created by `attach_test_disk`
        :param node_name: Node to detach disk from
        """
        pass

    @abstractmethod
    def get_ingress_and_api_vips(self) -> dict:
        pass

    @abstractmethod
    def destroy_all_nodes(self) -> None:
        pass

    @abstractmethod
    def get_cluster_network(self) -> str:
        pass

    @abstractmethod
    def setup_time(self) -> str:
        pass

    @abstractmethod
    def prepare_nodes(self):
        pass

    @abstractmethod
    def is_active(self, node_name) -> bool:
        pass

    @abstractmethod
    def set_boot_order(self, node_name, cd_first=False) -> None:

        pass

    @abstractmethod
    def set_per_device_boot_order(self, node_name, key: Callable[[Disk], int]) -> None:
        """
        Set the boot priority for every disk
        It sorts the disk according to the key function result
        :param node_name: The node to change its boot order
        :param key: a key function that gets a Disk object and decide it's priority
        """
        pass

    @abstractmethod
    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        pass

    @abstractmethod
    def set_single_node_ip(self, ip) -> None:
        pass

    @abstractmethod
    def get_host_id(self, node_name: str) -> str:
        pass

    @abstractmethod
    def get_cpu_cores(self, node_name: str) -> int:
        pass

    @abstractmethod
    def set_cpu_cores(self, node_name: str, core_count: int) -> None:
        pass

    @abstractmethod
    def get_ram_kib(self, node_name: str) -> int:
        pass

    @abstractmethod
    def set_ram_kib(self, node_name: str, ram_kib: int) -> None:
        pass

    def get_primary_machine_cidr(self) -> Optional[str]:
        # Default to auto resolve by the cluster. see cluster.get_primary_machine_cidr
        return None

    def get_provisioning_cidr(self) -> Optional[str]:
        return None

    @abstractmethod
    def attach_interface(self, node_name, network_xml: str) -> Tuple[libvirt.virNetwork, str]:
        pass

    @abstractmethod
    def add_interface(self, node_name, network_name, target_interface: str) -> str:
        pass

    @abstractmethod
    def undefine_interface(self, node_name: str, mac: str):
        pass

    @abstractmethod
    def create_network(self, network_xml: str) -> libvirt.virNetwork:
        pass

    @abstractmethod
    def get_network_by_name(self, network_name: str) -> libvirt.virNetwork:
        pass

    @abstractmethod
    def destroy_network(self, network: libvirt.virNetwork):
        pass

    def notify_iso_ready(self) -> None:
        pass

    def set_dns(self, api_vip: str, ingress_vip: str) -> None:
        pass

    def set_dns_for_user_managed_network(self) -> None:
        pass
