import os
import shutil

import consts
from assisted_test_infra.test_infra import utils
from service_client import InventoryClient, log


class IPXEController:
    def __init__(
        self,
        api_client: InventoryClient,
        name: str = None,
        port: int = consts.DEFAULT_IPXE_SERVER_PORT,
        ip: str = consts.DEFAULT_IPXE_SERVER_IP,
    ):
        self._name = name
        self._ip = ip
        self._port = port
        self._api_client = api_client
        self._dir = os.path.dirname(os.path.realpath(__file__))
        self._ipxe_scripts_folder = f"{self._dir}/server/ipxe_scripts"

    def remove(self):
        log.info(f"Removing iPXE Server {self._name}")
        utils.remove_running_container(container_name=self._name)
        self._remove_ipxe_scripts_folder()

    def start(self, infra_env_id: str, cluster_name: str):
        log.info("Preparing iPXE server")
        self._download_ipxe_script(infra_env_id=infra_env_id, cluster_name=cluster_name)
        self._build_server_image()
        self.run_ipxe_server()

    def run_ipxe_server(self):
        log.info(f"Running iPXE Server {self._name}")
        run_flags = [
            "-d",
            "--network=host",
            f"--publish {self._port}:{self._port}",
        ]
        utils.run_container(container_name=self._name, image=self._name, flags=run_flags)

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
