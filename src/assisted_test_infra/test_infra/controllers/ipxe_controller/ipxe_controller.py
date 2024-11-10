import copy
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
        local_pxe_assets: bool = False,
        empty_pxe_content: bool = False,
    ):
        super().__init__(name, port, name)
        self._ip = ip
        self._api_client = api_client
        self._local_pxe_assets = local_pxe_assets
        self._dir = os.path.dirname(os.path.realpath(__file__))
        self._ipxe_scripts_folder = f"{self._dir}/server/ipxe_scripts"
        self._empty_pxe_content = empty_pxe_content

    def _on_container_start(self, infra_env_id: str, cluster_name: str):
        log.info("Preparing iPXE server")
        self._download_ipxe_script(infra_env_id=infra_env_id, cluster_name=cluster_name)
        self._build_server_image()

    def _on_container_removed(self):
        self._remove_ipxe_scripts_folder()

    def _build_server_image(self):
        log.info(f"Creating Image for iPXE Server {self._name}")
        build_flags = f"--build-arg SERVER_IP={self._ip} --build-arg SERVER_PORT={self._port}"
        utils.run_command(f"podman-remote build {self._dir}/server -t {self._name} {build_flags}")

    def _download_ipxe_script(self, infra_env_id: str, cluster_name: str):
        log.info(f"Downloading iPXE script to {self._ipxe_scripts_folder}")
        utils.recreate_folder(self._ipxe_scripts_folder, force_recreate=False)
        pxe_content = ""
        if not self._empty_pxe_content:
            pxe_content = self._api_client.client.v2_download_infra_env_files(
                infra_env_id=infra_env_id, file_name="ipxe-script", _preload_content=False
            ).data.decode("utf-8")

            # PXE can not boot from http redirected to https, update the assets images to local http server
            if self._local_pxe_assets:
                pxe_content = self._download_ipxe_assets(pxe_content)

        with open(f"{self._ipxe_scripts_folder}/{cluster_name}", "w") as _file:
            _file.writelines(pxe_content)

    @staticmethod
    def _replace_assets_pxe(pxe_content: str, old_asset: str, new_asset: str):
        log.info(f"Replace pxe assets {old_asset} to {new_asset}")
        return pxe_content.replace(old_asset, new_asset)

    def _download_ipxe_assets(self, pxe_content: str) -> str:
        """Download the ipxe assets to the container http server
        Update the ipxe-script assets download from the container.
        The new asset will be downloaded from http://{self._ip}:{self._port}
        return new updated pxe content.
        """

        # New pxe content replace http links to local http server
        new_pxe_content = copy.deepcopy(pxe_content)
        new_asset = f"http://{self._ip}:{self._port}/"
        http_to_download = [res for res in pxe_content.split() if "http:" in res]
        for http in http_to_download:
            http = http[http.index("http") :]  # in case http not at the beginning
            for img in ["pxe-initrd", "kernel", "rootfs"]:
                if img in http:
                    utils.download_file(
                        url=http,
                        local_filename=f"{self._ipxe_scripts_folder}/{img}",
                        verify_ssl=False,
                    )
                    new_pxe_content = self._replace_assets_pxe(new_pxe_content, http, new_asset + img)
        return new_pxe_content

    def _remove_ipxe_scripts_folder(self):
        log.info(f"Removing iPXE scripts folder {self._ipxe_scripts_folder}")
        if os.path.exists(self._ipxe_scripts_folder):
            path = os.path.abspath(self._ipxe_scripts_folder)
            shutil.rmtree(path)
