import os
import shutil

import consts
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.containerized_controller import ContainerizedController
from service_client import InventoryClient, log


class IPXEController(ContainerizedController):
    def __init__(
        self,
        api_client: InventoryClient,
        name: str = None,
        port: int = consts.DEFAULT_IPXE_SERVER_PORT,
        ip: str = consts.DEFAULT_IPXE_SERVER_IP,
    ):
        super().__init__(name, port, name)
        self._ip = ip
        self._api_client = api_client
        self._dir = os.path.dirname(os.path.realpath(__file__))
        self._ipxe_scripts_folder = f"{self._dir}/server/ipxe_scripts"

    def _on_container_start(self, infra_env_id: str, cluster_name: str):
        log.info("Preparing iPXE server")
        self._download_ipxe_script(infra_env_id=infra_env_id, cluster_name=cluster_name)
        self._build_server_image()

    def _on_container_removed(self):
        self._remove_ipxe_scripts_folder()

    def _build_server_image(self):
        log.info(f"Creating Image for iPXE Server {self._name}")
        build_flags = f"--build-arg SERVER_IP={self._ip} --build-arg SERVER_PORT={self._port}"
        utils.run_command(f"podman {consts.PODMAN_FLAGS} build {self._dir}/server -t {self._name} {build_flags}")

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
