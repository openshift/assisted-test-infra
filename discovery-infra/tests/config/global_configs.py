from pathlib import Path
from typing import Any, ClassVar

from assisted_service_client import models
from dataclasses import dataclass

from test_infra.consts import env_defaults
from test_infra.utils import get_kubeconfig_path
from test_infra.utils.cluster_name import ClusterName
from test_infra.utils.infra_env_name import InfraEnvName
from test_infra.utils.global_variables import GlobalVariables
from test_infra.helper_classes.config import BaseClusterConfig, BaseInfraEnvConfig, BaseTerraformConfig


global_variables = GlobalVariables()


@dataclass
class ClusterConfig(BaseClusterConfig):
    """ A Cluster configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)

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


@dataclass
class InfraEnvConfig(BaseInfraEnvConfig):
    """ A Cluster configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)

    @staticmethod
    def _get_iso_download_path(infra_env_name: str):
        return str(
            Path(env_defaults.DEFAULT_IMAGE_FOLDER).joinpath(
                f"{infra_env_name}-{env_defaults.DEFAULT_IMAGE_FILENAME}"
            )
        ).strip()

    def __post_init__(self):
        super().__post_init__()
        if self.infra_env_name is None or isinstance(self.infra_env_name, str):
            self.infra_env_name = InfraEnvName()
        if self.iso_download_path is None:
            self.iso_download_path = self._get_iso_download_path(self.infra_env_name.get())


@dataclass
class Day2ClusterConfig(ClusterConfig):
    _details: ClassVar[models.cluster.Cluster] = None
    day1_cluster_name: ClusterName = None

    def get_copy(self):
        return Day2ClusterConfig(**self.get_all())

    def __post_init__(self):
        super(BaseClusterConfig, self).__post_init__()
        api_client = global_variables.get_api_client()
        self._details = api_client.cluster_get(self.cluster_id)
        if self.day1_cluster_name is None:
            raise ValueError("Invalid day1_cluster_name, got None")

        self.cluster_name = ClusterName(prefix=self._details.name)
        if self.iso_download_path is None:
            self.iso_download_path = self._get_iso_download_path(self.day1_cluster_name.get())


@dataclass
class TerraformConfig(BaseTerraformConfig):
    """ A Nodes configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)
