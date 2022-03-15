from contextlib import suppress
from dataclasses import dataclass
from typing import Any, ClassVar

from assisted_test_infra.test_infra.helper_classes.config.base_config import Triggerable
from assisted_test_infra.test_infra.utils import EnvVar, utils
from service_client import ClientFactory, InventoryClient
from tests.global_variables.env_variables_defaults import _EnvVariables
from triggers import Trigger, get_default_triggers


@dataclass(frozen=True)
class DefaultVariables(_EnvVariables, Triggerable):
    __instance: ClassVar = None

    def __getattribute__(self, item):
        """Keep __getattribute__ normal behavior for all class attributes but the EnvVar objects.
        If the return value supposed to be of type EnvVar it returns EnvVar.value instead, This makes the EnvVar
        mechanism transparent to whoever uses DefaultVariables instance"""

        attr = super().__getattribute__(item)
        if isinstance(attr, EnvVar):
            return attr.value
        return attr

    def __post_init__(self):
        client = None
        if not self.is_kube_api:
            with suppress(RuntimeError, TimeoutError):
                client = self.get_api_client()
        self._set("openshift_version", utils.get_openshift_version(allow_default=True, client=client))
        Trigger.trigger_configurations([self], get_default_triggers())

    def is_user_set(self, item: str) -> bool:
        return self.get_env(item).is_user_set

    def _set(self, key: str, value: Any):
        if not hasattr(self, key):
            raise AttributeError(f"Invalid key {key}")

        object.__setattr__(self, key, value)

    def _get_data_pool(self) -> object:
        return self

    def get_env(self, item: str) -> EnvVar:
        return _EnvVariables.__getattribute__(self, item)

    def get_api_client(self, offline_token=None, **kwargs) -> InventoryClient:
        url = self.remote_service_url
        offline_token = offline_token or self.offline_token

        if not url:
            url = utils.get_local_assisted_service_url(self.namespace, "assisted-service", self.deploy_target)

        return ClientFactory.create_client(url, offline_token, **kwargs)
