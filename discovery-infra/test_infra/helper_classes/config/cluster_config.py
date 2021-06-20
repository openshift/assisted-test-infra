from abc import ABC
from typing import List, Any

from dataclasses import dataclass

from .base_config import _BaseConfig

from test_infra.utils.cluster_name import ClusterName


@dataclass
class BaseClusterConfig(_BaseConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during it's execution
    All arguments must have default to None with type hint
    """
    pull_secret: str = None
    ssh_public_key: str = None
    openshift_version: str = None
    cluster_id: str = None
    cluster_name: ClusterName = None
    additional_ntp_source: str = None
    user_managed_networking: bool = None
    high_availability_mode: str = None
    hyperthreading: str = None
    olm_operators: List[str] = None
    base_dns_domain: str = None  # Todo - Might change during MGMT-5370
    vip_dhcp_allocation: bool = None
    iso_download_path: str = None  # Todo - Might change during MGMT-5370
    iso_image_type: str = None
    nodes_count: int = None  # Todo - Might change during MGMT-5370
    masters_count: int = None  # Todo - Might change during MGMT-5370
    workers_count: int = None  # Todo - Might change during MGMT-5370
    download_image: bool = None
    platform: str = None
    is_static_ip: bool = None
    is_ipv6: bool = None  # Todo - Might change during MGMT-5370
    service_network_cidr: str = None
    cluster_network_cidr: str = None
    cluster_network_host_prefix: int = None
    kubeconfig_path: str = None
