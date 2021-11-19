from abc import ABC, abstractmethod
from copy import copy
from typing import Any, Dict, Tuple

from frozendict import frozendict
from logger import log
from test_infra.consts import NetworkType, consts, resources

_default_triggers = frozendict(
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
        (("is_ipv4", True), ("is_ipv6", False),): {
            "cluster_networks": consts.DEFAULT_CLUSTER_NETWORKS_IPV4,
            "service_networks": consts.DEFAULT_SERVICE_NETWORKS_IPV4,
        },
        (("is_ipv4", False), ("is_ipv6", True),): {
            "cluster_networks": consts.DEFAULT_CLUSTER_NETWORKS_IPV6,
            "service_networks": consts.DEFAULT_SERVICE_NETWORKS_IPV6,
            "vip_dhcp_allocation": False,
            "openshift_version": consts.OpenshiftVersion.VERSION_4_8.value,
            "network_type": consts.NetworkType.OVNKubernetes,
        },
        (("is_ipv4", True), ("is_ipv6", True),): {
            "cluster_networks": consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            "service_networks": consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
            "network_type": consts.NetworkType.OVNKubernetes,
        },
        (("network_type", NetworkType.OVNKubernetes),): {
            "vip_dhcp_allocation": False,
        },
    }
)


class Triggerable(ABC):
    @classmethod
    def get_default_triggers(cls) -> Dict[Tuple[Tuple[str, Any]], Dict[str, Any]]:
        return copy(_default_triggers)

    def trigger(self, triggers: Dict[Tuple[Tuple[str, Any]], Dict[str, Any]] = None):
        if triggers is None:
            triggers = self.get_default_triggers()

        for conditions, values in triggers.items():
            assert isinstance(conditions, tuple) and all(
                isinstance(condition, tuple) for condition in conditions
            ), f"Key {conditions} must be tuple of tuples"

            if all(self._is_set(param, expected_value) for param, expected_value in conditions):
                self._handle_trigger(conditions, values)

    def _is_set(self, var, expected_value):
        return getattr(self, var, None) == expected_value

    def _handle_trigger(self, conditions: Tuple[Tuple[str, Any]], values: Dict[str, Any]) -> None:
        for k, v in values.items():
            self._set(k, v)
        log.info(f"{conditions} is triggered. Updating global variables: {values}")

    @abstractmethod
    def _set(self, key: str, value: Any):
        pass
