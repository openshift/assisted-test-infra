import logging
from test_infra.controllers.node_controllers import ssh
from test_infra import consts


class Node(object):

    def __init__(self, name, node_controller, private_ssh_key_path=None, username="core"):
        self.name = name
        self.private_ssh_key_path = private_ssh_key_path
        self.username = username
        self.node_controller = node_controller
        self._ips = []
        self._macs = []

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.node_controller.is_active(self.name)

    def is_master_in_name(self):
        return consts.NodeRoles.MASTER in self.name

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

    def run_command(self, bash_command, background=False):
        output = ""
        if not self.node_controller.is_active:
            raise Exception("%s is not active, can't run given command")
        with ssh.SshConnection(self.ips[0], private_ssh_key_path=self.private_ssh_key_path,
                               username=self.username) as run:
            if background:
                run.background_script(bash_command)
            else:
                output = run.script(bash_command, verbose=False)
        return output

    def shutdown(self):
        return self.node_controller.shutdown_node(self.name)

    def start(self):
        return self.node_controller.start_node(self.name)

    def restart(self):
        self.shutdown()
        self.start()

    def reset(self):
        logging.info("Resetting host %s", self.name)
        self.shutdown()
        self.format_disk()
        self.start()

    def format_disk(self):
        self.node_controller.format_node_disk(self.name)

    def kill_service(self, service):
        logging.info("Killing service %s on host %s", service, self.name)
        self.run_command(f'sudo systemctl kill {service}.service || true')

    def kill_podman_container_by_name(self, container_name):
        output = self.run_command(f"sudo su root -c 'podman ps | grep {container_name}'")
        logging.info(f"Container details on {self.name}: provided container name: {container_name}, output: "
                     f"\n {output}")
        logging.info(f"Killing container: {container_name}")
        output = self.run_command(f"sudo su root -c 'podman kill {container_name}'")
        logging.info(f"Output of kill container command: {output}")

    def is_service_active(self, service):
        logging.info("Verifying if service %s is active on host %s", service, self.name)
        output = self.run_command(f'sudo systemctl is-active {service}.service || true')
        return output.strip() == "active"

    def set_boot_order(self, cd_first=False):
        logging.info("Setting boot order with cd_first=%s on %s", cd_first, self.name)
        self.node_controller.set_boot_order(node_name=self.name, cd_first=cd_first)

    def set_boot_order_flow(self, cd_first=False, start=True):
        self.shutdown()
        self.set_boot_order(cd_first)
        if start:
            self.start()
