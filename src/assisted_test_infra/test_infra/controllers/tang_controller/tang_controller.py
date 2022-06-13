import socket
from time import sleep

import consts
from assisted_test_infra.test_infra import utils
from service_client import log


class TangController:
    """
    TangController deploys a Tang server inside container which running on hypervisor, port 7500
    It allows deploying AI OCP cluster encrypted with tang mode
    """

    def __init__(self, name: str = None, port: int = consts.DEFAULT_TANG_SERVER_PORT, pull_secret: str = None):
        self._name = name
        self._port = port
        self.ip = None
        self.address = None
        self.thumbprint = None
        self._pull_secret = pull_secret
        self._image = "registry.redhat.io/rhel8/tang"
        self._set_server_address()

    def remove(self):
        log.info(f"Removing Tang Server {self._name}")
        utils.remove_running_container(container_name=self._name)

    def _set_server_address(self):
        host_name = socket.gethostname()
        self.ip = socket.gethostbyname(host_name)
        self.address = f"http://{self.ip}:{self._port}"

    def _create_auth_file(self):
        filename = f"{consts.WORKING_DIR}/{self._name}_authfile"
        with open(filename, "w") as opened_file:
            opened_file.write(self._pull_secret)
        return filename

    def run_tang_server(self):
        log.info(f"Running Tang Server {self._name}")
        auth_file = self._create_auth_file()
        run_flags = [
            "-d",
            "--restart=always",
            "--network=host",
            f"-e PORT={self._port}",
            f"--publish {self._port}:{self._port}",
            f"--authfile={auth_file}",
        ]
        utils.run_container(container_name=self._name, image=self._image, flags=run_flags)

        for _ in range(100):
            try:
                out, err, retval = utils.run_command(["podman", "ps"])
                log.info(f"({out}, {err}, {retval})")
            except Exception as e:
                log.exception(f"({out}, {err}, {retval}): {e}")

            sleep(5)

    def set_thumbprint(self):
        exec_command = (
            f"podman --cgroup-manager=cgroupfs --storage-driver=vfs --events-backend=file "
            f"exec -it {self._name} tang-show-keys {self._port}"
        )
        self.thumbprint, _, _ = utils.run_command(exec_command, shell=True)
