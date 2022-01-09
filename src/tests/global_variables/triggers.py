from typing import Any, Dict, Tuple

from frozendict import frozendict

from consts import consts, resources

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
            "network_type": consts.NetworkType.OVNKubernetes,
        },
        (("is_ipv4", True), ("is_ipv6", True),): {
            "cluster_networks": consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            "service_networks": consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
            "network_type": consts.NetworkType.OVNKubernetes,
        },
        (("network_type", consts.NetworkType.OVNKubernetes),): {
            "vip_dhcp_allocation": False,
        },
    }
)


def get_default_triggers() -> Dict[Tuple[Tuple[str, Any]], Dict[str, Any]]:
    """Make _triggers read only"""
    return _default_triggers
