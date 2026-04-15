import threading
import time
from typing import Any, Callable, List, Optional, Tuple

import kfish
import libvirt
import waiting

from assisted_test_infra.test_infra import BaseClusterConfig, utils
from assisted_test_infra.test_infra.controllers.node_controllers.adapter_controller import AdapterController
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from assisted_test_infra.test_infra.helper_classes.config.base_redfish_config import BaseRedfishConfig
from service_client import log
from src.service_client import InventoryClient

SUCCESS = 204


class RedfishReceiver:

    def __init__(self, host: str, config: BaseRedfishConfig):
        self.user = config.redfish_user
        self.password = config.redfish_password
        self.receivers = config.redfish_machines
        self._config = config
        self.host = host.strip()

        try:
            self.redfish = self.redfish_init(self.host)
        except Exception as e:
            raise e

    def redfish_init(self, host):
        return kfish.Redfish(host, user=self.user, password=self.password, debug=True)


class RedfishEjectIso:

    @classmethod
    def execute(cls, receiver: RedfishReceiver):
        log.info(f"{cls.__name__}: {receiver.__dict__}")
        iso, inserted = receiver.redfish.get_iso_status()
        log.info(f"{cls.__name__}: eject status: {iso} {inserted}")
        try:
            receiver.redfish.eject_iso()
        except Exception as e:
            log.info(f"{cls.__name__}: eject iso fails {e}")


class RedfishInsertIso:

    @classmethod
    def execute(cls, receiver: RedfishReceiver, nfs_iso):
        log.info(f"{cls.__name__} inserting iso {nfs_iso}")
        try:
            receiver.redfish.insert_iso(nfs_iso)
        except Exception as e:
            log.info(f"{cls.__name__}: insert iso fails {e}")


class RedfishSetIsoOnce:

    @classmethod
    def execute(cls, receiver: RedfishReceiver):
        try:
            log.info(f"{cls.__name__}: {receiver.__dict__}")
            receiver.redfish.set_iso_once()
        except Exception as e:
            log.info(f"Receiver host {receiver.host} failed to set iso once: {str(e)}")


class RedfishRestart:

    @classmethod
    def execute(cls, receiver: RedfishReceiver):
        log.info(f"{cls.__name__}: {receiver.__dict__}")
        receiver.redfish.restart()


class RedfishReset:

    @classmethod
    def execute(cls, receiver: RedfishReceiver):
        log.info(f"{cls.__name__}: {receiver.__dict__}")
        receiver.redfish.reset()


class RedfishController(NodeController):
    """Manage Dell's baremetal nodes.

    Allow to use baremetal machines directly by calling to racadm utils.
    It allows us to manage node - setting boot , reboot nodes and boot from iso.
    """

    IDRAC_WAIT = 60 * 3
    IDRAC_RETRY = 30
    IDRAC_RESET_RECOVER = 60 * 4

    _config: BaseRedfishConfig

    def __init__(self, config: BaseNodesConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self.redfish_receivers = [RedfishReceiver(host, self._config) for host in self._config.redfish_machines]
        self.nfs_mount = None
        self._node_adapter = None

    @staticmethod
    def _nfs_server_local():
        # Assume NFS server enabled on  /tmp/test_images/, return external interface address for nfs mount
        command = """ip route get 1 | awk '{ printf  $7 }'"""
        cmd_out, _, _ = utils.run_command(command, shell=True)
        return cmd_out

    @staticmethod
    def _is_idrac_state(receiver: RedfishReceiver, states: list) -> bool:
        try:
            hostname = receiver.redfish.url.split("/")[2]
            current_state = receiver.redfish.info()["BootProgress"]["LastState"]
            log.info(f"Is idrac {hostname} status: {states}| current_state: {current_state}")
            return current_state in states
        except Exception as e:
            log.info(e)
            return False

    def _stop_idrac_node(self, receiver: RedfishReceiver):
        receiver.redfish.stop()
        waiting.wait(
            lambda: self._is_idrac_state(receiver, ["None", "Node already powered off"]),
            timeout_seconds=self.IDRAC_WAIT,
            sleep_seconds=self.IDRAC_RETRY,
            waiting_for="Stopping IDRAC service",
        )

    def _start_idrac_node(self, receiver: RedfishReceiver):
        receiver.redfish.start()
        waiting.wait(
            lambda: self._is_idrac_state(receiver, ["OSRunning"]),
            timeout_seconds=self.IDRAC_WAIT,
            sleep_seconds=self.IDRAC_RETRY,
            waiting_for="Starting IDRAC service",
        )

    def _reset_idrac_node(self, receiver: RedfishReceiver):
        receiver.redfish.reset()
        # During reset no connectivity - ~3 minutes restart
        time.sleep(self.IDRAC_RESET_RECOVER)

        waiting.wait(
            lambda: self._is_idrac_state(receiver, ["OSRunning"]),
            timeout_seconds=self.IDRAC_WAIT,
            sleep_seconds=self.IDRAC_RETRY,
            waiting_for="Reset IDRAC service",
        )

    def stop_idrac(self, receivers: list[RedfishReceiver]):
        for receiver in receivers:
            self._stop_idrac_node(receiver)

    def reset_idrac(self, receivers: list[RedfishReceiver]):
        start_threads = []
        for redfish in receivers:
            t = threading.Thread(target=self._reset_idrac_node, args=(redfish,))
            start_threads.append(t)
            t.start()  # Start immediately so they all run at the same time
        for t in start_threads:
            t.join()

    def start_idrac(self, receivers: list[RedfishReceiver]):
        for receiver in receivers:
            self._start_idrac_node(receiver)

    def list_nodes(self) -> List[Node]:
        if self._node_adapter:
            return self._node_adapter.list_nodes()
        return []

    def list_disks(self, node_name: str) -> List[dict]:
        if self._node_adapter:
            return self._node_adapter.list_disks(node_name)
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

    def set_nfs_mount_path(self, host, image_path) -> str:
        log.info(f"{type(self).__name__} host {host} set mount path {image_path}")
        self.nfs_mount = f"{host}:{image_path}"

    def set_adapter_controller(self, inventory_client: InventoryClient):
        self._node_adapter = AdapterController(inventory_client, self._config, self._entity_config)

    def prepare_nodes(self):
        if not self.nfs_mount:
            self.set_nfs_mount_path(self._nfs_server_local(), self._entity_config.iso_download_path)

        # Reset idrac and start from  clean without leftovers - ~3.5 minutes
        if not self._node_adapter:
            self.set_adapter_controller(self.inventory_client)
        self.reset_idrac(self.redfish_receivers)
        for receiver in self.redfish_receivers:
            RedfishEjectIso.execute(receiver)
            # ISO image shared by NFS by default
            RedfishSetIsoOnce.execute(receiver)
            RedfishInsertIso.execute(receiver, self.nfs_mount)

        for receiver_restart in self.redfish_receivers:
            RedfishRestart.execute(receiver_restart)

    def is_active(self, node_name) -> bool:
        return self._node_adapter.is_active(node_name)

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
        return self._node_adapter.get_node_ips_and_macs(node_name)

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
