import json
from abc import ABC
from typing import List, Optional

from assisted_test_infra.test_infra.utils import utils
from service_client import log


class ContainerizedController(ABC):
    def __init__(self, name: str, port: int, image: str, extra_flags: Optional[List[str]] = None) -> None:
        self._name = name
        self._port = port
        self._image = image
        self._extra_flags = [] if not extra_flags else extra_flags
        self._is_running = False
        self._container_id = None

    def run(self, **kwargs):
        if self._is_running:
            log.info(f"{self.__class__.__name__} server is already running...")
            return
        log.info(f"Running {self.__class__.__name__} Server {self._name}")

        self._is_running = True
        self._on_container_start(**kwargs)
        base_run_flags = [
            "-d",
            "--restart=always",
            "--network=host",
            f"--publish {self._port}:{self._port}",
        ]

        utils.run_container(container_name=self._name, image=self._image, flags=base_run_flags + self._extra_flags)

    @property
    def container_id(self):
        # Cached container id when created.
        if not self._is_running:
            raise RuntimeError("Unable to get container id when container is not running ")

        if self._container_id is None:
            podman_filter_name = f"podman-remote ps -f name={self._name} --format json"
            out = utils.run_command(podman_filter_name, shell=True)[0]
            podman_id = json.loads(out)[0]["Id"]
            self._container_id = podman_id

        return self._container_id

    def write_to_container(self, file_path_container: str, content: list[str], append: bool = False) -> None:
        # Write to file inside the container - update running container
        container_id = self.container_id

        redirect_append = ">>"
        redirect_override = ">"
        empty = "\n"
        exec_container = f"podman-remote exec -it {container_id} /bin/sh -c"

        if not append:
            # Reset file content if not append
            utils.run_command(f"{exec_container} 'echo {empty}{redirect_override}{file_path_container}'", shell=True)

        for line in content:
            utils.run_command(f"{exec_container} 'echo {line}{redirect_append}{file_path_container}'", shell=True)

    def copy_file_to_container(self, local_file_path: str, container_file_path: str) -> None:
        # Copy file from local hypervisor to the running container
        container_id = self.container_id

        exec_container = f"podman-remote cp {local_file_path}  {container_id}:{container_file_path}"
        utils.run_command(f"{exec_container}", shell=True)

    def remove(self):
        if self._is_running:
            log.info(f"Removing containerized {type(self)} Server {self._name}")
            utils.remove_running_container(container_name=self._name)
            self._on_container_removed()
            self._is_running = False
        else:
            log.info(f"Skipping Removing containerized {type(self)} Server {self._name}")

    def _on_container_removed(self):
        """Can be overridden to clear configurations after the controller container was removed"""
        pass

    def _on_container_start(self, **kwargs):
        """Can be overridden to run some logic before the container started"""
        pass
