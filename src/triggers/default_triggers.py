from typing import Dict

from frozendict import frozendict

from consts import consts, resources
from triggers.env_trigger import Trigger
from triggers.olm_operators_trigger import OlmOperatorsTrigger

_default_triggers = frozendict(
    {
        "remote_deployment": Trigger(
            conditions=[lambda config: config.remote_service_url is not None], worker_disk=consts.DISK_SIZE_100GB
        ),
        "none_platform": Trigger(
            conditions=[lambda config: config.platform == consts.Platforms.NONE],
            user_managed_networking=True,
            tf_platform=consts.Platforms.NONE,
        ),
        "vsphere_platform": Trigger(
            conditions=[lambda config: config.platform == consts.Platforms.VSPHERE],
            user_managed_networking=False,
            tf_platform=consts.Platforms.VSPHERE,
        ),
        "nutanix_platform": Trigger(
            conditions=[lambda config: config.platform == consts.Platforms.NUTANIX],
            tf_platform=consts.Platforms.NUTANIX,
        ),
        "oci_platform": Trigger(
            conditions=[lambda config: config.platform == consts.Platforms.OCI],
            user_managed_networking=True,
            tf_platform=consts.Platforms.OCI,
        ),
        "sno": Trigger(
            conditions=[lambda config: config.masters_count == 1],
            workers_count=0,
            high_availability_mode=consts.HighAvailabilityMode.NONE,
            user_managed_networking=True,
            master_memory=resources.DEFAULT_MASTER_SNO_MEMORY,
            master_vcpu=resources.DEFAULT_MASTER_SNO_CPU,
            network_type=None,
        ),
        "ipv4": Trigger(
            conditions=[lambda config: config.is_ipv4 is True and config.is_ipv6 is False],
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4,
        ),
        "ipv6": Trigger(
            conditions=[lambda config: config.is_ipv4 is False and config.is_ipv6 is True],
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV6,
        ),
        "ipv6_required_configurations": Trigger(
            conditions=[lambda config: config.is_ipv6 is True],
            network_type=consts.NetworkType.OVNKubernetes,
        ),
        "OVNKubernetes": Trigger(
            conditions=[lambda config: config.network_type == consts.NetworkType.OVNKubernetes],
        ),
        "dualstack": Trigger(
            conditions=[lambda config: config.is_ipv4 is True and config.is_ipv6 is True],
            cluster_networks=consts.DEFAULT_CLUSTER_NETWORKS_IPV4V6,
            service_networks=consts.DEFAULT_SERVICE_NETWORKS_IPV4V6,
        ),
        # to be removed
        "ocs_operator": OlmOperatorsTrigger(conditions=[lambda config: "ocs" in config.olm_operators], operator="ocs"),
        "lso_operator": OlmOperatorsTrigger(conditions=[lambda config: "lso" in config.olm_operators], operator="lso"),
        "metallb_operator": OlmOperatorsTrigger(
            conditions=[lambda config: "metallb" in config.olm_operators], operator="metallb"
        ),
        "cnv_operator": OlmOperatorsTrigger(conditions=[lambda config: "cnv" in config.olm_operators], operator="cnv"),
        "odf_operator": OlmOperatorsTrigger(conditions=[lambda config: "odf" in config.olm_operators], operator="odf"),
        "lvm_operator": OlmOperatorsTrigger(conditions=[lambda config: "lvm" in config.olm_operators], operator="lvm"),
        "sno_mce_operator": OlmOperatorsTrigger(
            conditions=[lambda config: "mce" in config.olm_operators, lambda config2: config2.masters_count == 1],
            operator="mce",
            is_sno=True,
        ),
        "mce_operator": OlmOperatorsTrigger(
            conditions=[lambda config: "mce" in config.olm_operators, lambda config2: config2.masters_count > 1],
            operator="mce",
        ),
        "ipxe_boot": Trigger(
            conditions=[lambda config: config.ipxe_boot is True],
            download_image=False,
            master_boot_devices=["hd", "network"],
            worker_boot_devices=["hd", "network"],
        ),
    }
)


def get_default_triggers() -> Dict[str, Trigger]:
    """Make _triggers read only"""
    return _default_triggers
