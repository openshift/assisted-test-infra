from typing import Dict

from frozendict import frozendict

from consts import consts, resources
from triggers.env_trigger import Trigger
from triggers.olm_operators_trigger import OlmOperatorsTrigger

_default_triggers = frozendict(
    {
        "none_platform": Trigger(
            ("platform", consts.Platforms.NONE), user_managed_networking=True, vip_dhcp_allocation=False
        ),
        "vsphere_platform": Trigger(("platform", consts.Platforms.VSPHERE), user_managed_networking=False),
        "sno": Trigger(
            ("masters_count", 1),
            workers_count=0,
            high_availability_mode=consts.HighAvailabilityMode.NONE,
            user_managed_networking=True,
            vip_dhcp_allocation=False,
            master_memory=resources.DEFAULT_MASTER_SNO_MEMORY,
            master_vcpu=resources.DEFAULT_MASTER_SNO_CPU,
        ),
        "ipv4": Trigger(
            (
                ("is_ipv4", True),
                ("is_ipv6", False),
            ),
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4,
        ),
        "ipv6": Trigger(
            (
                ("is_ipv4", False),
                ("is_ipv6", True),
            ),
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV6,
        ),
        "ipv6_only": Trigger(
            ("is_ipv6", True), vip_dhcp_allocation=False, network_type=consts.NetworkType.OVNKubernetes
        ),
        "dualstack": Trigger(
            (
                ("is_ipv4", True),
                ("is_ipv6", True),
            ),
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
        ),
        "ocs_operator": OlmOperatorsTrigger("ocs"),
        "lso_operator": OlmOperatorsTrigger("lso"),
        "cnv_operator": OlmOperatorsTrigger("cnv"),
    }
)


def get_default_triggers() -> Dict[str, Trigger]:
    """Make _triggers read only"""
    return _default_triggers