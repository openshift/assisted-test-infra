from typing import Dict

from frozendict import frozendict

from consts import consts, resources
from triggers.env_trigger import Trigger
from triggers.olm_operators_trigger import OlmOperatorsTrigger

_default_triggers = frozendict(
    {
        "remote_deployment": Trigger(
            condition=lambda config: config.remote_service_url is not None, worker_disk=consts.DISK_SIZE_120GB
        ),
        "none_platform": Trigger(
            condition=lambda config: config.platform == consts.Platforms.NONE,
            user_managed_networking=True,
            vip_dhcp_allocation=False,
        ),
        "vsphere_platform": Trigger(
            condition=lambda config: config.platform == consts.Platforms.VSPHERE, user_managed_networking=False
        ),
        "sno": Trigger(
            condition=lambda config: config.masters_count == 1,
            workers_count=0,
            high_availability_mode=consts.HighAvailabilityMode.NONE,
            user_managed_networking=True,
            vip_dhcp_allocation=False,
            master_memory=resources.DEFAULT_MASTER_SNO_MEMORY,
            master_vcpu=resources.DEFAULT_MASTER_SNO_CPU,
            network_type=consts.NetworkType.OVNKubernetes,
        ),
        "ipv4": Trigger(
            condition=lambda config: config.is_ipv4 is True and config.is_ipv6 is False,
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4,
        ),
        "ipv6": Trigger(
            condition=lambda config: config.is_ipv4 is False and config.is_ipv6 is True,
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV6,
        ),
        "ipv6_required_configurations": Trigger(
            condition=lambda config: config.is_ipv6 is True,
            vip_dhcp_allocation=False,
            network_type=consts.NetworkType.OVNKubernetes,
        ),
        "OVNKubernetes": Trigger(
            condition=lambda config: config.network_type == consts.NetworkType.OVNKubernetes,
            vip_dhcp_allocation=False,
        ),
        "dualstack": Trigger(
            condition=lambda config: config.is_ipv4 is True and config.is_ipv6 is True,
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
        ),
        "ocs_operator": OlmOperatorsTrigger(condition=lambda config: "ocs" in config.olm_operators, operator="ocs"),
        "lso_operator": OlmOperatorsTrigger(condition=lambda config: "lso" in config.olm_operators, operator="lso"),
        "cnv_operator": OlmOperatorsTrigger(condition=lambda config: "cnv" in config.olm_operators, operator="cnv"),
        "odf_operator": OlmOperatorsTrigger(condition=lambda config: "odf" in config.olm_operators, operator="odf"),
        "ipxe_boot": Trigger(
            condition=lambda config: config.ipxe_boot is True,
            download_image=False,
            master_boot_devices=["hd", "network"],
            worker_boot_devices=["hd", "network"],
        ),
    }
)


def get_default_triggers() -> Dict[str, Trigger]:
    """Make _triggers read only"""
    return _default_triggers
