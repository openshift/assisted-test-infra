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

    def run(self, **kwargs):
        if self._is_running:
            log.info(f"{self.__class__.__name__} server is already running...")
            return
        log.info(f"Running {self.__class__.__name__} Server {self._name}")

        self._on_container_start(**kwargs)
        base_run_flags = [
            "-d",
            "--restart=always",
            "--network=host",
            f"--publish {self._port}:{self._port}",
        ]

        utils.run_container(container_name=self._name, image=self._image, flags=base_run_flags + self._extra_flags)
        self._is_running = True

    def remove(self):
        if self._is_running:
            log.info(f"Removing Proxy Server {self._name}")
            utils.remove_running_container(container_name=self._name)
            self._on_container_removed()
            self._is_running = False

    def _on_container_removed(self):
        """Can be overridden to clear configurations after the controller container was removed"""
        pass

    def _on_container_start(self, **kwargs):
        """Can be overridden to run some logic before the container started"""
        pass
