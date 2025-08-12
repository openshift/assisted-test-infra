import json
from typing import Any, Callable, List, Optional, Tuple

import libvirt

from assisted_test_infra.test_infra import BaseEntityConfig
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig
from service_client import log


class AdapterController(NodeController):
    """The adapter controller is based on created cluster inventory.

    In case a controller does not support interfaces / disk show command

    Taking the information from cluster hosts and set them as controller info.
    Will allow us to ssh / modify bootable disks when controller api missing.

    """

    def __init__(self, cluster: dict, config: BaseNodesConfig, entity_config: BaseEntityConfig):
        super().__init__(config, entity_config)
        self._cluster = cluster
        self.private_ssh_key_path = config.private_ssh_key_path

    def log_configuration(self):
        log.info(f"controller configuration={self._config}")

    @property
    def workers_count(self):
        return self._config.workers_count

    @property
    def masters_count(self):
        return self._config.masters_count

    @property
    def arbiters_count(self):
        return self._config.arbiters_count

    @property
    def is_ipv4(self):
        return self._config.is_ipv4

    @property
    def is_ipv6(self):
        return self._config.is_ipv6

    @property
    def tf_platform(self):
        return self._config.tf_platform

    @property
    def load_balancer_type(self):
        return self._config.load_balancer_type

    def list_nodes(self) -> List[Node]:
        nodes_list = []
        try:
            for host in self._cluster.get_details().hosts:
                nodes_list.append(
                    Node(host.requested_hostname, self._cluster.nodes.controller, self.private_ssh_key_path)
                )
            return nodes_list
        except Exception as e:
            log.info(f"Unable to list nodes {str(e)}")
            return nodes_list

    def list_disks(self, node_name: str) -> List[dict]:
        try:
            for host in self._cluster.get_details().hosts:
                if host.requested_hostname == node_name:
                    disks = json.loads(host.inventory)["disks"]
                    return disks
            return {}
        except Exception as e:
            log.info(f"Unable to list disks {str(e)}")
            return {}

    def list_networks(self) -> List[Any]:
        pass

    def list_leases(self, network_name: str) -> List[Any]:
        pass

    def shutdown_node(self, node_name: str) -> None:
        pass

    def shutdown_all_nodes(self) -> None:
        pass

    def start_node(self, node_name: str, check_ips: bool) -> None:
        pass

    def start_all_nodes(self) -> List[Node]:
        pass

    def restart_node(self, node_name: str) -> None:
        pass

    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        pass

    def format_all_node_disks(self) -> None:
        pass

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

    def detach_all_test_disks(self, node_name: str):
        """
        Detaches all test disks created by `attach_test_disk`
        :param node_name: Node to detach disk from
        """
        pass

    def get_ingress_and_api_vips(self) -> dict:
        pass

    def destroy_all_nodes(self) -> None:
        pass

    def get_cluster_network(self) -> str:
        pass

    def setup_time(self) -> str:
        pass

    def prepare_nodes(self):
        pass

    def is_active(self, node_name: str) -> bool:
        try:
            for host in self._cluster.get_details().hosts:
                if host.requested_hostname == node_name:
                    if host.status not in ["disconnected"]:
                        return True
            return False
        except Exception as e:
            log.info(f"Unable to is active {str(e)}")
            return False

    def set_boot_order(self, node_name: str, cd_first: bool = False, cdrom_iso_path: str = None) -> None:
        pass

    def set_per_device_boot_order(self, node_name, key: Callable[[Disk], int]) -> None:
        """
        Set the boot priority for every disk
        It sorts the disk according to the key function result
        :param node_name: The node to change its boot order
        :param key: a key function that gets a Disk object and decide it's priority
        """
        pass

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        ips = []
        macs = []
        try:
            for host in self._cluster.get_details().hosts:
                if host.requested_hostname == node_name:
                    interfaces = json.loads(host.inventory)["interfaces"]
                    for i in interfaces:
                        ips.extend(i["ipv4_addresses"])
                        macs.append(i["mac_address"])
            ips = [ip.split("/")[0] for ip in ips]
            return ips, macs
        except Exception as e:
            log.info(f"Unable to get node ips and mac {str(e)}")
            return ips, macs

    def set_single_node_ip(self, ip) -> None:
        pass

    def get_host_id(self, node_name: str) -> str:
        pass

    def get_cpu_cores(self, node_name: str) -> int:
        pass

    def set_cpu_cores(self, node_name: str, core_count: int) -> None:
        pass

    def get_ram_kib(self, node_name: str) -> int:
        pass

    def set_ram_kib(self, node_name: str, ram_kib: int) -> None:
        pass

    def get_primary_machine_cidr(self) -> Optional[str]:
        # Default to auto resolve by the cluster. see cluster.get_primary_machine_cidr
        return None

    def get_provisioning_cidr(self) -> Optional[str]:
        return None

    def attach_interface(self, node_name, network_xml: str) -> Tuple[libvirt.virNetwork, str]:
        pass

    def add_interface(self, node_name, network_name, target_interface: str) -> str:
        pass

    def undefine_interface(self, node_name: str, mac: str):
        pass

    def create_network(self, network_xml: str) -> libvirt.virNetwork:
        pass

    def get_network_by_name(self, network_name: str) -> libvirt.virNetwork:
        pass

    def wait_till_nodes_are_ready(self, network_name: str = None):
        """If not overridden - do not wait"""
        pass

    def destroy_network(self, network: libvirt.virNetwork):
        pass

    def notify_iso_ready(self) -> None:
        pass

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        pass

    def set_dns_for_user_managed_network(self) -> None:
        pass

    def set_ipxe_url(self, network_name: str, ipxe_url: str):
        pass

    def get_day2_static_network_data(self):
        pass
