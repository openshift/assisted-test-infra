import os
import shutil
from abc import ABC
from typing import List, Tuple

from paramiko import SSHException
from scp import SCPException

from assisted_test_infra.test_infra import BaseClusterConfig, utils
from assisted_test_infra.test_infra.controllers.node_controllers import ssh
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig
from service_client import log


class ZVMController(NodeController, ABC):
    _entity_config: BaseClusterConfig

    def __init__(self, config: BaseNodesConfig, cluster_config: BaseClusterConfig):
        super().__init__(config, cluster_config)
        self.cluster_name = cluster_config.cluster_name.get()
        self._dir = os.path.dirname(os.path.realpath(__file__))
        self._ipxe_scripts_folder = f"{self._dir}/zVM/ipxe_scripts"
        self._cfg_node_path = ""

    @property
    def ssh_connection(self):
        if not self._entity_config.zvm_bastion_host:
            raise RuntimeError("Bastion host not configured")

        log.info(f"Trying to accessing bastion host {self._entity_config.zvm_bastion_host}")
        for ip in self.ips:
            exception = None
            try:
                connection = ssh.SshConnection(
                    ip, private_ssh_key_path=self.private_ssh_key_path, username=self.username
                )
                connection.connect()
                return connection

            except (TimeoutError, SCPException, SSHException) as e:
                log.warning("Could not SSH through IP %s: %s", ip, str(e))
                exception = e

        if exception is not None:
            raise exception

    # for zVm nodes only iPXE scripts are supported due to the lack of ISO support
    def _download_ipxe_script(self, infra_env_id: str, cluster_name: str):
        log.info(f"Downloading iPXE script to {self._ipxe_scripts_folder}")
        utils.recreate_folder(self._ipxe_scripts_folder, force_recreate=False)
        self._api_client.download_and_save_infra_env_file(
            infra_env_id=infra_env_id, file_name="ipxe-script", file_path=f"{self._ipxe_scripts_folder}/{cluster_name}"
        )

    def _remove_ipxe_scripts_folder(self):
        log.info(f"Removing iPXE scripts folder {self._ipxe_scripts_folder}")
        if os.path.exists(self._ipxe_scripts_folder):
            path = os.path.abspath(self._ipxe_scripts_folder)
            shutil.rmtree(path)

    def get_cfg_node_path(self):
        log.info(f"Node configuration path: {self._cfg_node_path}")
        return self._cfg_node_path

    def set_cfg_node_path(self, cfg_path):
        log.info(f"New node configuration path: {cfg_path}")
        self._cfg_node_path = cfg_path

    def list_nodes(self) -> List[Node]:
        return None

    def list_disks(self, node_name: str) -> List[Disk]:
        return None

    def list_networks(self):
        return None

    def list_leases(self):
        return None

    # No shutdown for zVM nodes
    def shutdown_node(self, node_name: str) -> None:
        return None

    # No shutdown for zVM nodes
    def shutdown_all_nodes(self) -> List[Node]:
        return None

    # No start for zVM nodes -> ipl instead
    def start_node(self, node_name: str, check_ips: bool) -> None:
        return None

    # No start for zVM nodes -> ipl instead
    def start_all_nodes(self) -> List[Node]:
        return None

    # restart means ipl and could be from reader or from disk
    def restart_node(self, node_name: str) -> None:
        return None

    # format of node disk might be a low level format (e.g. DASD devices - this might take a long time -> timeout)
    def format_node_disk(self, node_name: str, disk_index: int = 0) -> None:
        return None

    # format of nodes might be a mix between regular format and low level format.
    def format_all_node_disks(self) -> None:
        return None

    # attach for zVM might be tricky or not possible due to missing cli support for zVM commands
    def attach_test_disk(self, node_name: str, disk_size: int, bootable=False, persistent=False, with_wwn=False):
        pass

    # as attach the detach of disks might be tricky (missing cli support for zVM commands)
    def detach_all_test_disks(self, node_name: str):
        pass

    def get_ingress_and_api_vips(self) -> dict:
        return None

    # destroy only for KVM possible not for zVM
    def destroy_all_nodes(self) -> None:
        pass

    def setup_time(self) -> str:
        return None

    # for zVM nodes, till now, only iPXE scripts are supported
    def prepare_nodes(self):
        log.info("Preparing nodes taken from cfg file (copy files to tmp of bastion)")
        if not os.path.exists(self._entity_config.zvm_node_cfg_path):
            self._clean_bastion()

    # clean tmp folder on bastion node
    def _clean_bastion(self):
        log.info("Remove existing parm files.")
        self.run_command("rm -rf /tmp/*.parm")

    def is_active(self, node_name) -> bool:
        return False

    def set_boot_order(self, node_name: str, cd_first: bool = False, cdrom_iso_path: str = None) -> None:
        return None

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        return None

    def set_single_node_ip(self, ip) -> None:
        return

    def get_host_id(self, node_name: str) -> str:
        return None

    def get_cpu_cores(self, node_name: str) -> int:
        return -1

    # for zVM nodes set CPU cores (e.g.: cp def cpu 5) will not work until cli support for
    # zVM commands is not implemented
    def set_cpu_cores(self, node_name: str, core_count: int) -> None:
        pass

    def get_ram_kib(self, node_name: str) -> int:
        return -1

    # for zVM nodes set storage (e.g.: cp def stor 16g) cores will not work until cli support for
    # zVM commands is not implemented
    def set_ram_kib(self, node_name: str, ram_kib: int) -> None:
        pass

    def get_primary_machine_cidr(self):
        # Default to auto resolve by the cluster. see cluster.get_primary_machine_cidr
        return None

    def get_provisioning_cidr(self):
        return None

    # attaching a network interface will not not work for zVM until missing cli support is implemented.
    def attach_interface(self, node_name, network_xml: str):
        return None

    def add_interface(self, node_name, network_name, target_interface: str) -> str:
        return None

    def undefine_interface(self, node_name: str, mac: str):
        return

    # for zVM there is no create network support
    def create_network(self, network_xml: str):
        pass

    # for zVM there is no get network (only for s390 KVM)
    def get_network_by_name(self, network_name: str):
        pass

    def wait_till_nodes_are_ready(self, network_name: str = None):
        """If not overridden - do not wait"""
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

    # destroying network only for KVM (zVM and LPAR will be handled via HMC)
    def destroy_network(self):
        pass

    def get_cluster_network(self):
        pass

    def set_per_device_boot_order(self):
        pass
