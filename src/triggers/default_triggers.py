from typing import Dict

from frozendict import frozendict

from consts import consts, resources
from triggers.env_trigger import Trigger
from triggers.olm_operators_trigger import OlmOperatorsTrigger

_default_triggers = frozendict(
    {
        "production": Trigger(
            condition=("remote_service_url", consts.RemoteEnvironment.PRODUCTION), worker_disk=consts.DISK_SIZE_120GB
        ),
        "staging": Trigger(
            condition=("remote_service_url", consts.RemoteEnvironment.STAGING), worker_disk=consts.DISK_SIZE_120GB
        ),
        "integration": Trigger(
            condition=("remote_service_url", consts.RemoteEnvironment.INTEGRATION), worker_disk=consts.DISK_SIZE_120GB
        ),
        "none_platform": Trigger(
            ("platform", consts.Platforms.NONE), user_managed_networking=True, vip_dhcp_allocation=False
        ),
        "vsphere_platform": Trigger(("platform", consts.Platforms.VSPHERE), user_managed_networking=False),
        "sno": Trigger(
            condition=("masters_count", 1),
            workers_count=0,
            high_availability_mode=consts.HighAvailabilityMode.NONE,
            user_managed_networking=True,
            vip_dhcp_allocation=False,
            master_memory=resources.DEFAULT_MASTER_SNO_MEMORY,
            master_vcpu=resources.DEFAULT_MASTER_SNO_CPU,
            network_type=consts.NetworkType.OVNKubernetes,
        ),
        "ipv4": Trigger(
            condition=(("is_ipv4", True), ("is_ipv6", False)),
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4,
        ),
        "ipv6": Trigger(
            condition=(("is_ipv4", False), ("is_ipv6", True)),
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV6,
        ),
        "ipv6_required_configurations": Trigger(
            condition=("is_ipv6", True), vip_dhcp_allocation=False, network_type=consts.NetworkType.OVNKubernetes
        ),
        "OVNKubernetes": Trigger(
            condition=("network_type", consts.NetworkType.OVNKubernetes),
            vip_dhcp_allocation=False,
        ),
        "dualstack": Trigger(
            condition=(("is_ipv4", True), ("is_ipv6", True)),
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
        ),
        "ocs_operator": OlmOperatorsTrigger(condition="ocs"),
        "lso_operator": OlmOperatorsTrigger(condition="lso"),
        "cnv_operator": OlmOperatorsTrigger(condition="cnv"),
        "odf_operator": OlmOperatorsTrigger(condition="odf"),
    }
)


def get_default_triggers() -> Dict[str, Trigger]:
    """Make _triggers read only"""
    return _default_triggers
