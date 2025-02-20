from pathlib import Path
from typing import Callable, Optional

from paramiko import SSHException
from scp import SCPException

import consts
from assisted_test_infra.test_infra.controllers.node_controllers import ssh
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from service_client import log


class Node:
    def __init__(
        self,
        name,
        node_controller,
        private_ssh_key_path: Optional[Path] = None,
        username="core",
        role: Optional[str] = None,
    ):
        self.name = name
        self.private_ssh_key_path = private_ssh_key_path
        self.username = username
        self.node_controller = node_controller
        self.original_vcpu_count = self.get_cpu_cores()
        self.original_ram_kib = self.get_ram_kib()
        self._ips = []
        self._macs = []
        self._role = role

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.node_controller.is_active(self.name)

    def is_master_in_name(self) -> bool:
        return self.role == consts.NodeRoles.MASTER

    def is_worker_in_name(self) -> bool:
        return self.role == consts.NodeRoles.WORKER

    @property
    def role(self) -> str:
        if self._role:
            return self._role

        if consts.NodeRoles.MASTER in self.name:
            return consts.NodeRoles.MASTER

        if consts.NodeRoles.WORKER in self.name:
            return consts.NodeRoles.WORKER

        return consts.NodeRoles.AUTO_ASSIGN

    def _set_ips_and_macs(self):
        self._ips, self._macs = self.node_controller.get_node_ips_and_macs(self.name)

    # TODO maybe add ttl? need mechanism that
    #  will zero this value when node is stopped
    @property
    def ips(self):
        if not self._ips:
            self._set_ips_and_macs()
        return self._ips

    @property
    def macs(self):
        if not self._macs:
            self._set_ips_and_macs()
        return self._macs

    @property
    def ssh_connection(self):
        if not self.ips:
            raise RuntimeError(f"No available IPs for node {self.name}")

        log.info("Trying to access through IP addresses: %s", ", ".join(self.ips))
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

    def upload_file(self, local_source_path, remote_target_path):
        with self.ssh_connection as _ssh:
            return _ssh.upload_file(local_source_path, remote_target_path)

    def download_file(self, remote_source_path, local_target_path):
        with self.ssh_connection as _ssh:
            return _ssh.download_file(remote_source_path, local_target_path)

    def run_command(self, bash_command, background=False):
        output = ""
        if not self.node_controller.is_active(self.name):
            raise RuntimeError("%s is not active, can't run given command")
        with self.ssh_connection as _ssh:
            if background:
                _ssh.background_script(bash_command)
            else:
                output = _ssh.script(bash_command, verbose=False)
        return output

    def shutdown(self):
        return self.node_controller.shutdown_node(self.name)

    def start(self, check_ips=True):
        return self.node_controller.start_node(self.name, check_ips)

    def restart(self):
        self.shutdown()
        self.start()

    def restart_service(self, service):
        log.info("Restarting service: %s on host %s", service, self.name)
        self.run_command(f"sudo systemctl restart {service}.service")

    def reset(self):
        log.info("Resetting host %s", self.name)
        self.shutdown()
        self.format_disk()
        self.start()

    def format_disk(self, disk_index: int = 0):
        self.node_controller.format_node_disk(self.name, disk_index)

    def kill_installer(self):
        self.kill_podman_container_by_name("assisted-installer")

    def kill_service(self, service):
        log.info("Killing service %s on host %s", service, self.name)
        self.run_command(f"sudo systemctl kill {service}.service || true")

    def kill_podman_container_by_name(self, container_name):
        output = self.run_command(f"sudo su root -c 'podman ps | grep {container_name}'")
        log.info(
            f"Container details on {self.name}: provided container name: {container_name}, output: " f"\n {output}"
        )
        log.info(f"Killing container: {container_name}")
        output = self.run_command(f"sudo su root -c 'podman kill {container_name}'")
        log.info(f"Output of kill container command: {output}")

    def is_service_active(self, service):
        log.info("Verifying if service %s is active on host %s", service, self.name)
        output = self.run_command(f"sudo systemctl is-active {service}.service || true")
        return output.strip() == "active"

    def set_boot_order(self, cd_first=False, cdrom_iso_path=None) -> None:
        log.info("Setting boot order with cd_first=%s on %s", cd_first, self.name)
        self.node_controller.set_boot_order(node_name=self.name, cd_first=cd_first, cdrom_iso_path=cdrom_iso_path)

    def set_per_device_boot_order(self, key: Callable[[Disk], int]):
        log.info("Setting boot order on %s", self.name)
        self.node_controller.set_per_device_boot_order(node_name=self.name, key=key)

    def set_boot_order_flow(self, cd_first=False, start=True):
        log.info("Setting boot order , cd_first=%s, start=%s", cd_first, start)
        self.shutdown()
        self.set_boot_order(cd_first)
        if start:
            self.start()

    def get_host_id(self):
        return self.node_controller.get_host_id(self.name)

    def get_cpu_cores(self):
        return self.node_controller.get_cpu_cores(self.name)

    def set_cpu_cores(self, core_count):
        self.node_controller.set_cpu_cores(self.name, core_count)

    def reset_cpu_cores(self):
        self.set_cpu_cores(self.original_vcpu_count)

    def get_ram_kib(self):
        return self.node_controller.get_ram_kib(self.name)

    def set_ram_kib(self, ram_kib):
        self.node_controller.set_ram_kib(self.name, ram_kib)

    def reset_ram_kib(self):
        self.set_ram_kib(self.original_ram_kib)

    def get_disks(self):
        return self.node_controller.list_disks(self.name)

    def attach_test_disk(self, disk_size, **kwargs):
        return self.node_controller.attach_test_disk(self.name, disk_size, **kwargs)

    def detach_all_test_disks(self):
        self.node_controller.detach_all_test_disks(self.name)

    def attach_interface(self, network_xml, target_interface=consts.TEST_TARGET_INTERFACE):
        return self.node_controller.attach_interface(self.name, network_xml, target_interface)

    def add_interface(self, network_name, target_interface=consts.TEST_TARGET_INTERFACE):
        return self.node_controller.add_interface(self.name, network_name, target_interface)

    def create_network(self, network_xml):
        return self.node_controller.create_network(network_xml)

    def get_network_by_name(self, network_name):
        return self.node_controller.get_network_by_name(network_name)

    def destroy_network(self, network):
        self.node_controller.destroy_network(network)

    def undefine_interface(self, mac):
        self.node_controller.undefine_interface(self.name, mac)
