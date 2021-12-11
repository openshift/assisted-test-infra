from contextlib import suppress
from typing import Any

from assisted_test_infra.test_infra.assisted_service_api import ClientFactory, InventoryClient
from assisted_test_infra.test_infra.utils import utils
from assisted_test_infra.test_infra.utils.global_variables.env_variables_defaults import _EnvVariablesDefaults
from assisted_test_infra.test_infra.utils.global_variables.triggerable import Triggerable


class GlobalVariables(_EnvVariablesDefaults, Triggerable):
    def __post_init__(self):
        super().__post_init__()
        client = None
        if not self.is_kube_api:
            with suppress(RuntimeError, TimeoutError):
                client = self.get_api_client()
        self._set("openshift_version", utils.get_openshift_version(allow_default=True, client=client))
        self.trigger(self.get_default_triggers())

    def _set(self, key: str, value: Any):
        _EnvVariablesDefaults._set(self, key, value)

    def __getattribute__(self, item):
        try:
            return super().__getattribute__(item)
        except BaseException:
            return None

    def get_api_client(self, offline_token=None, **kwargs) -> InventoryClient:
        url = self.remote_service_url
        offline_token = offline_token or self.offline_token

        if not url:
            url = utils.get_local_assisted_service_url(
                self.namespace, "assisted-service", utils.get_env("DEPLOY_TARGET")
            )

        return ClientFactory.create_client(url, offline_token, **kwargs)
