from abc import ABC
from typing import List

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
    base_dns_domain: str = None
    vip_dhcp_allocation: bool = None
    iso_download_path: str = None
    iso_image_type: str = None
    download_image: bool = None
    platform: str = None
    is_static_ip: bool = None
    service_network_cidr: str = None
    cluster_network_cidr: str = None
    cluster_network_host_prefix: int = None
    kubeconfig_path: str = None
    network_type: str = None
