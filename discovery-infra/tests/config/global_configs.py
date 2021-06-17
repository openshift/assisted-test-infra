from typing import Any

from dataclasses import dataclass

from test_infra.utils.global_variables import GlobalVariables
from test_infra.helper_classes.config import BaseClusterConfig, BaseTerraformConfig

global_variables = GlobalVariables()


@dataclass
class ClusterConfig(BaseClusterConfig):
    """ A Cluster configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)


@dataclass
class TerraformConfig(BaseTerraformConfig):
    """ A Nodes configuration with defaults that obtained from EnvConfig """

    @staticmethod
    def get_default(key, default=None) -> Any:
        return getattr(global_variables, key)
