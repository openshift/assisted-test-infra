from abc import ABC
from pathlib import Path
from typing import Dict, List

from dataclasses import dataclass, field
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
    worker_cpu_mode: str = None
    master_cpu_mode: str = None
    network_mtu: int = None
    worker_disk: int = None
    master_disk: int = None
    master_disk_count: int = None
    worker_disk_count: int = None
    storage_pool_path: str = None
    # running: bool = True
    single_node_ip: str = None
    dns_records: Dict[str, str] = field(default_factory=dict)

    libvirt_master_ips: List[str] = None
    libvirt_secondary_master_ips: List[str] = None
    libvirt_worker_ips: List[str] = None
    libvirt_secondary_worker_ips: List[str] = None

    private_ssh_key_path: Path = None
    network_name: str = None
    net_asset: Munch = None
    platform: str = None
    base_dns_domain: str = None  # base_domain
    is_ipv6: bool = None  # ipv6
    tf_folder: str = None
    bootstrap_in_place: bool = None

    def __post_init__(self):
        super().__post_init__()
