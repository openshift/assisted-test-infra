from dataclasses import dataclass

from assisted_test_infra.test_infra import (
    BaseClusterConfig,
    BaseDay2ClusterConfig,
    BaseInfraEnvConfig,
    BaseNutanixConfig,
    BaseTerraformConfig,
    BaseVSphereConfig,
    ClusterName,
    InfraEnvName,
    utils,
)
from tests.global_variables import DefaultVariables

global_variables = DefaultVariables()


def reset_global_variables():
    global global_variables
    global_variables = DefaultVariables()


@dataclass
class ClusterConfig(BaseClusterConfig):
    """A Cluster configuration with defaults that obtained from EnvConfig"""

    def _get_data_pool(self):
        return global_variables

    def __post_init__(self):
        super().__post_init__()
        if self.cluster_name is None or isinstance(self.cluster_name, str):
            self.cluster_name = ClusterName()  # todo rm cluster_name after removing config.cluster_name dependencies
        if self.kubeconfig_path is None:
            self.kubeconfig_path = utils.get_kubeconfig_path(self.cluster_name.get())


@dataclass
class InfraEnvConfig(BaseInfraEnvConfig):
    """A Cluster configuration with defaults that obtained from EnvConfig"""

    def _get_data_pool(self):
        return global_variables

    def __post_init__(self):
        super(BaseInfraEnvConfig, self).__post_init__()
        if self.entity_name is None or isinstance(self.entity_name, str):
            self.entity_name = InfraEnvName()
        if self.iso_download_path is None:
            self.iso_download_path = utils.get_iso_download_path(self.entity_name.get())


@dataclass
class Day2ClusterConfig(BaseDay2ClusterConfig):
    """A day2 Cluster configuration with defaults that obtained from EnvConfig"""

    def _get_data_pool(self):
        return global_variables

    def __post_init__(self):
        super().__post_init__()

        if self.cluster_name is None or isinstance(self.cluster_name, str):
            self.cluster_name = ClusterName()  # todo rm cluster_name after removing config.cluster_name dependencies
        self.entity_name = self.cluster_name
        if self.iso_download_path is None:
            self.iso_download_path = utils.get_iso_download_path(self.entity_name.get())


@dataclass
class TerraformConfig(BaseTerraformConfig):
    """A Nodes configuration with defaults that obtained from EnvConfig"""

    def _get_data_pool(self):
        return global_variables


@dataclass
class VSphereConfig(BaseVSphereConfig):
    """A Nodes configuration with defaults that obtained from EnvConfig"""

    def _get_data_pool(self):
        return global_variables


@dataclass
class NutanixConfig(BaseNutanixConfig):
    """A Nodes configuration with defaults that obtained from EnvConfig"""

    def _get_data_pool(self):
        return global_variables
