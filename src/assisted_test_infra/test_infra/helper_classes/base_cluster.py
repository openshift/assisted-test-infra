from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from assisted_service_client import models
from junit_report import JunitTestCase

from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, Nodes
from assisted_test_infra.test_infra.helper_classes.entity import Entity
from assisted_test_infra.test_infra.helper_classes.infra_env import InfraEnv
from service_client import InventoryClient, log


class BaseCluster(Entity, ABC):
    _config: BaseClusterConfig

    def __init__(
        self,
        api_client: InventoryClient,
        config: BaseClusterConfig,
        infra_env_config: BaseInfraEnvConfig,
        nodes: Optional[Nodes] = None,
    ):
        self._infra_env_config = infra_env_config
        self._infra_env: Optional[InfraEnv] = None

        super().__init__(api_client, config, nodes)

        # Update infraEnv configurations
        self._infra_env_config.cluster_id = config.cluster_id
        self._infra_env_config.openshift_version = self._config.openshift_version
        self._infra_env_config.pull_secret = self._config.pull_secret

    @property
    def id(self) -> str:
        return self._config.cluster_id

    def get_details(self) -> Union[models.infra_env.InfraEnv, models.cluster.Cluster]:
        return self.api_client.cluster_get(self.id)

    @abstractmethod
    def start_install_and_wait_for_installed(self, **kwargs):
        pass

    def download_image(self, iso_download_path: str = None, static_network_config=None) -> Path:
        if self._infra_env is None:
            log.warning("No infra_env found. Generating infra_env and downloading ISO")
            return self.generate_and_download_infra_env(
                static_network_config=static_network_config,
                iso_download_path=iso_download_path or self._config.iso_download_path,
                iso_image_type=self._config.iso_image_type,
            )
        return self._infra_env.download_image(iso_download_path or self._config.iso_download_path)

    @JunitTestCase()
    def generate_and_download_infra_env(
        self,
        iso_download_path=None,
        static_network_config=None,
        iso_image_type=None,
        ssh_key=None,
        ignition_info=None,
        proxy=None,
    ) -> Path:
        self.generate_infra_env(
            static_network_config=static_network_config,
            iso_image_type=iso_image_type,
            ssh_key=ssh_key,
            ignition_info=ignition_info,
            proxy=proxy,
        )
        return self.download_infra_env_image(iso_download_path=iso_download_path or self._config.iso_download_path)

    def generate_infra_env(
        self, static_network_config=None, iso_image_type=None, ssh_key=None, ignition_info=None, proxy=None
    ) -> InfraEnv:
        if self._infra_env:
            return self._infra_env

        self._infra_env = self.create_infra_env(static_network_config, iso_image_type, ssh_key, ignition_info, proxy)
        return self._infra_env

    def download_infra_env_image(self, iso_download_path=None) -> Path:
        iso_download_path = iso_download_path or self._config.iso_download_path
        log.debug(f"Downloading ISO to {iso_download_path}")
        return self._infra_env.download_image(iso_download_path=iso_download_path)

    def create_infra_env(
        self, static_network_config=None, iso_image_type=None, ssh_key=None, ignition_info=None, proxy=None
    ) -> InfraEnv:
        self._infra_env_config.ssh_public_key = ssh_key or self._config.ssh_public_key
        self._infra_env_config.iso_image_type = iso_image_type or self._config.iso_image_type
        self._infra_env_config.static_network_config = static_network_config
        self._infra_env_config.ignition_config_override = ignition_info
        self._infra_env_config.proxy = proxy or self._config.proxy
        infra_env = InfraEnv(api_client=self.api_client, config=self._infra_env_config)
        return infra_env

    def set_pull_secret(self, pull_secret: str, cluster_id: str = None):
        log.info(f"Setting pull secret:{pull_secret} for cluster: {self.id}")
        self.update_config(pull_secret=pull_secret)
        self.api_client.update_cluster(cluster_id or self.id, {"pull_secret": pull_secret})

    def get_iso_download_path(self, iso_download_path: str = None):
        return iso_download_path or self._infra_env_config.iso_download_path
