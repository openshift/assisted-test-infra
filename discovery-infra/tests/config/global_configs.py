from typing import Any

from dataclasses import dataclass

from .env_config import EnvConfig
from test_infra.helper_classes.config import BaseClusterConfig, BaseTerraformConfig


@dataclass
class ClusterConfig(BaseClusterConfig):
    """ A Cluster configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return EnvConfig.get(key, default)


@dataclass
class TerraformConfig(BaseTerraformConfig):
    """ A Nodes configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return EnvConfig.get(key, default)
