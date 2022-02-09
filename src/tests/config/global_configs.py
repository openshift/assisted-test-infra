from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assisted_test_infra.test_infra import (
    BaseClusterConfig,
    BaseDay2ClusterConfig,
    BaseInfraEnvConfig,
    BaseTerraformConfig,
    ClusterName,
    InfraEnvName,
    utils,
)
from consts import env_defaults
from tests.global_variables import DefaultVariables

global_variables = DefaultVariables()


@dataclass
class ClusterConfig(BaseClusterConfig):
    """A Cluster configuration with defaults that obtained from EnvConfig"""

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)

    @staticmethod
    def _get_iso_download_path(cluster_name: str):
        return str(
            Path(env_defaults.DEFAULT_IMAGE_FOLDER).joinpath(f"{cluster_name}-{env_defaults.DEFAULT_IMAGE_FILENAME}")
        ).strip()

    def __post_init__(self):
        super().__post_init__()
        if self.cluster_name is None or isinstance(self.cluster_name, str):
            self.cluster_name = ClusterName()  # todo rm cluster_name after removing config.cluster_name dependencies
        self.entity_name = self.cluster_name
        if self.kubeconfig_path is None:
            self.kubeconfig_path = utils.get_kubeconfig_path(self.cluster_name.get())
        if self.iso_download_path is None:
            self.iso_download_path = self._get_iso_download_path(self.cluster_name.get())


@dataclass
class InfraEnvConfig(BaseInfraEnvConfig):
    """A Cluster configuration with defaults that obtained from EnvConfig"""

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)

    @staticmethod
    def _get_iso_download_path(infra_env_name: str):
        return str(
            Path(env_defaults.DEFAULT_IMAGE_FOLDER).joinpath(f"{infra_env_name}-{env_defaults.DEFAULT_IMAGE_FILENAME}")
        ).strip()

    def __post_init__(self):
        super().__post_init__()
        if self.entity_name is None or isinstance(self.entity_name, str):
            self.entity_name = InfraEnvName()
        if self.iso_download_path is None:
            self.iso_download_path = self._get_iso_download_path(self.entity_name.get())


@dataclass
class Day2ClusterConfig(BaseDay2ClusterConfig):
    """A day2 Cluster configuration with defaults that obtained from EnvConfig"""

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)


@dataclass
class TerraformConfig(BaseTerraformConfig):
    """A Nodes configuration with defaults that obtained from EnvConfig"""

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)
