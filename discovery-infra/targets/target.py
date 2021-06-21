from abc import ABC, abstractmethod

from test_infra import utils
from test_infra.assisted_service_api import InventoryClient, ClientFactory
from test_infra.tools.assets import LibvirtNetworkAssets
from test_infra.utils.global_variables import GlobalVariables
from tests.config import TerraformConfig, ClusterConfig


def get_api_client(namespace: str, remote_service_url: str, offline_token=None, **kwargs) -> InventoryClient:
    if not remote_service_url:
        remote_service_url = utils.get_local_assisted_service_url(
            namespace, "assisted-service", utils.get_env("DEPLOY_TARGET"))

    return ClientFactory.create_client(remote_service_url, offline_token, **kwargs)


class Target(ABC):
    def __init__(self):
        net_asset = LibvirtNetworkAssets()
        self._global_variables: GlobalVariables = GlobalVariables()
        self._cluster_config: ClusterConfig = ClusterConfig()
        self._terraform_config: TerraformConfig = TerraformConfig(net_asset=net_asset.get())
        self._api_client: InventoryClient = get_api_client(self._global_variables.namespace,
                                                           self._global_variables.remote_service_url,
                                                           self._global_variables.offline_token)

    @abstractmethod
    def run(self):
        pass
