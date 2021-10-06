from contextlib import suppress
from typing import ClassVar, List

from frozendict import frozendict
from logger import log
from test_infra import consts
from test_infra.assisted_service_api import ClientFactory, InventoryClient
from test_infra.consts import resources
from test_infra.utils import utils
from test_infra.utils.global_variables.env_variables_defaults import \
    _EnvVariablesDefaults

_triggers = frozendict(
    {
        (("platform", consts.Platforms.NONE),): {
            "user_managed_networking": True,
            "vip_dhcp_allocation": False,
        },
        (("platform", consts.Platforms.VSPHERE),): {
            "user_managed_networking": False,
        },
        (("masters_count", 1),): {
            "workers_count": 0,
            "nodes_count": 1,
            "high_availability_mode": consts.HighAvailabilityMode.NONE,
            "user_managed_networking": True,
            "vip_dhcp_allocation": False,
            "openshift_version": consts.OpenshiftVersion.VERSION_4_8.value,
            "master_memory": resources.DEFAULT_MASTER_SNO_MEMORY,
            "master_vcpu": resources.DEFAULT_MASTER_SNO_CPU,
        },
        (("is_ipv4", False), ("is_ipv6", True),): {
            "cluster_networks": consts.DEFAULT_CLUSTER_NETWORKS_IPV6,
            "service_networks": consts.DEFAULT_SERVICE_NETWORKS_IPV6,
            "vip_dhcp_allocation": False,
            "openshift_version": consts.OpenshiftVersion.VERSION_4_8.value,
            "network_type": consts.NetworkType.OVNKubernetes
        },
        (("is_ipv4", True), ("is_ipv6", True),): {
            "cluster_networks": consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            "service_networks": consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
            "network_type": consts.NetworkType.OVNKubernetes,
        }
    }
)


class GlobalVariables(_EnvVariablesDefaults):
    _triggered: ClassVar[List[str]] = list()

    def __post_init__(self):
        super().__post_init__()
        client=None
        if not self.is_kube_api:
            with suppress(RuntimeError, TimeoutError):
                client=self.get_api_client()
        self._set("openshift_version", utils.get_openshift_version(allow_default=True, client=client))

        for conditions, values in _triggers.items():
            assert isinstance(conditions, tuple) and isinstance(conditions[0], tuple), f"Key {conditions} must be tuple of tuples"
            if all(map(lambda condition: self.is_set(condition[0], condition[1]), conditions)):
                self._handle_trigger(conditions, values)

    def is_set(self, var, expected):
        return getattr(self, var) == expected

    def _handle_trigger(self, conditions, values):
        for k, v in values.items():
            self._set(k, v)

        self._triggered.append(conditions)
        log.info(f"{conditions} is triggered. Updating global variables: {values}")

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
                self.namespace, 'assisted-service', utils.get_env('DEPLOY_TARGET'))

        return ClientFactory.create_client(url, offline_token, **kwargs)
