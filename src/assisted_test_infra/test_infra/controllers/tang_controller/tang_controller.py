import socket

import consts
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.containerized_controller import ContainerizedController


class TangController(ContainerizedController):
    """
    TangController deploys a Tang server inside container which running on hypervisor, port 7500
    It allows deploying AI OCP cluster encrypted with tang mode
    """

    IMAGE = "registry.redhat.io/rhel8/tang"

    def __init__(self, name: str = None, port: int = consts.DEFAULT_TANG_SERVER_PORT, pull_secret: str = None):
        extra_flags = [f"-e PORT={port}", f"--authfile={self._create_auth_file(name, pull_secret)}"]
        super().__init__(name, port, self.IMAGE, extra_flags)
        self.ip = None
        self.address = None
        self.thumbprint = None
        self._set_server_address()

    def _set_server_address(self):
        host_name = socket.gethostname()
        self.ip = socket.gethostbyname(host_name)
        self.address = f"http://{self.ip}:{self._port}"

    @classmethod
    def _create_auth_file(cls, name: str, pull_secret: str):
        filename = f"{consts.WORKING_DIR}/{name}_authfile"
        with open(filename, "w") as opened_file:
            opened_file.write(pull_secret)
        return filename

    def set_thumbprint(self):
        exec_command = f"podman-remote exec -it {self._name} tang-show-keys {self._port}"
        self.thumbprint, _, _ = utils.run_command(exec_command, shell=True, local_only=True)
