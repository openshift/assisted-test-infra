from pathlib import Path
from typing import Any, ClassVar

from assisted_service_client import models
from dataclasses import dataclass

from test_infra.assisted_service_api import InventoryClient, ClientFactory
from test_infra.consts import env_defaults
from test_infra.utils import get_kubeconfig_path, utils
from test_infra.utils.cluster_name import ClusterName
from test_infra.utils.global_variables import GlobalVariables
from test_infra.helper_classes.config import BaseClusterConfig, BaseTerraformConfig

global_variables = GlobalVariables()


@dataclass
class ClusterConfig(BaseClusterConfig):
    """ A Cluster configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)

    def get_copy(self):
        return ClusterConfig(**self.get_all())

    @staticmethod
    def _get_iso_download_path(cluster_name: str):
        return str(
            Path(env_defaults.DEFAULT_IMAGE_FOLDER).joinpath(
                f"{cluster_name}-{env_defaults.DEFAULT_IMAGE_FILENAME}"
            )
        ).strip()

    def __post_init__(self):
        super().__post_init__()
        if self.cluster_name is None or isinstance(self.cluster_name, str):
            self.cluster_name = ClusterName()
        if self.kubeconfig_path is None:
            self.kubeconfig_path = get_kubeconfig_path(self.cluster_name.get())
        if self.iso_download_path is None:
            self.iso_download_path = self._get_iso_download_path(self.cluster_name.get())


def get_api_client(offline_token=None, **kwargs) -> InventoryClient:
    url = global_variables.remote_service_url
    offline_token = offline_token or global_variables.offline_token

    if not url:
        url = utils.get_local_assisted_service_url(
            global_variables.namespace, 'assisted-service', utils.get_env('DEPLOY_TARGET'))

    return ClientFactory.create_client(url, offline_token, **kwargs)


@dataclass
class Day2ClusterConfig(ClusterConfig):
    _details: ClassVar[models.cluster.Cluster] = None
    day1_cluster_name: ClusterName = None

    def get_copy(self):
        return Day2ClusterConfig(**self.get_all())

    def __post_init__(self):
        super(BaseClusterConfig, self).__post_init__()
        api_client = get_api_client()
        self._details = api_client.cluster_get(self.cluster_id)
        if self.day1_cluster_name is None:
            raise ValueError("Invalid day1_cluster_name, got None")

        self.cluster_name = ClusterName(prefix=self._details.name)
        if self.iso_download_path is None:
            self.iso_download_path = self._get_iso_download_path(self.day1_cluster_name.get())


@dataclass
class TerraformConfig(BaseTerraformConfig):
    """ A Nodes configuration with defaults that obtained from EnvConfig """

    def get_copy(self):
        return TerraformConfig(**self.get_all())

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)
