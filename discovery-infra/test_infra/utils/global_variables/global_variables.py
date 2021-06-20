from typing import ClassVar, List

from frozendict import frozendict

from test_infra import consts
from test_infra.utils.global_variables.env_variables_utils import _EnvVariablesUtils


_triggers = frozendict({
    ("platform", consts.Platforms.NONE): {
        "user_managed_networking": True,
        "vip_dhcp_allocation": False
    },
    ("masters_count", 1): {
        "high_availability_mode": consts.HighAvailabilityMode.NONE,
        "user_managed_networking": True,
        "vip_dhcp_allocation": False,
        "openshift_version": consts.OpenshiftVersion.VERSION_4_8.value
    },
    ("is_ipv6", True): {
        "service_network_cidr": consts.DEFAULT_IPV6_SERVICE_CIDR,
        "cluster_network_cidr": consts.DEFAULT_IPV6_CLUSTER_CIDR,
        "cluster_network_host_prefix": consts.DEFAULT_IPV6_HOST_PREFIX,
        "vip_dhcp_allocation": False
    }
})


class GlobalVariables(_EnvVariablesUtils):
    _triggered: ClassVar[List[str]] = list()

    def __post_init__(self):
        super().__post_init__()

        for (env, expected), values in _triggers.items():
            is_triggered = False
            if getattr(self, env) == expected:
                for k, v in values.items():
                    self._set(k, v)
                    is_triggered = True

            if is_triggered:
                self._triggered.append(env)

    def __getattribute__(self, item):
        try:
            return super().__getattribute__(item)
        except BaseException:
            return None
