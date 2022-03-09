import functools
from typing import Optional

from assisted_service_client import ApiClient
from kubernetes.client import ApiClient as KubeApiClient
from kubernetes.client import Configuration as KubeConfiguration
from kubernetes.config import load_kube_config

import consts
from service_client import InventoryClient
from service_client.logger import log


class ClientFactory:
    @staticmethod
    @functools.cache
    def create_client(
        url: str,
        offline_token: str,
        pull_secret: Optional[str] = "",
        wait_for_api: Optional[bool] = True,
        timeout: Optional[int] = consts.WAIT_FOR_BM_API,
    ) -> InventoryClient:
        log.info("Creating assisted-service client for url: %s", url)
        c = InventoryClient(url, offline_token, pull_secret)
        if wait_for_api:
            c.wait_for_api_readiness(timeout)
        return c

    @staticmethod
    def create_kube_api_client(kubeconfig_path: Optional[str] = None) -> ApiClient:
        log.info("creating kube client with config file: %s", kubeconfig_path)

        conf = KubeConfiguration()
        load_kube_config(config_file=kubeconfig_path, client_configuration=conf)
        return KubeApiClient(configuration=conf)
