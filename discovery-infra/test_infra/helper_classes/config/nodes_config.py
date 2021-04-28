from abc import ABC
from typing import List

from dataclasses import dataclass
from munch import Munch

from .base_config import _BaseConfig


@dataclass
class BaseTerraformConfig(_BaseConfig, ABC):
    """
    Define all configurations variables that are needed for Nodes during it's execution
    All arguments must have default to None with type hint
    """
    worker_memory: int = None
    master_memory: int = None
    worker_vcpu: int = None
    master_vcpu: int = None
    workers_count: int = None
    masters_count: int = None
    network_mtu: int = None
    worker_disk: str = None
    master_disk: str = None
    storage_pool_path: str = None
    # running: bool = True
    single_node_ip: str = None
    olm_operators: List = None

    libvirt_master_ips: List = None
    libvirt_secondary_master_ips: List = None
    libvirt_worker_ips: List = None
    libvirt_secondary_worker_ips: List = None

    private_ssh_key_path: str = None
    cluster_name: str = None
    network_name: str = None
    net_asset: Munch = None
    platform: str = None
    base_dns_domain: str = None  # base_domain
    is_ipv6: bool = None  # ipv6
    tf_folder: str = None
    iso_download_path: str = None
    bootstrap_in_place: bool = None
