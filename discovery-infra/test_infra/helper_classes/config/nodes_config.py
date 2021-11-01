from abc import ABC
from dataclasses import dataclass, field
from typing import Dict, List

from munch import Munch

from .controller_config import BaseNodeConfig


@dataclass
class BaseTerraformConfig(BaseNodeConfig, ABC):
    """
    Define all configurations variables that are needed for Nodes during it's execution
    All arguments must have default to None with type hint
    """

    single_node_ip: str = None
    dns_records: Dict[str, str] = field(default_factory=dict)

    libvirt_master_ips: List[str] = None
    libvirt_secondary_master_ips: List[str] = None
    libvirt_worker_ips: List[str] = None
    libvirt_secondary_worker_ips: List[str] = None

    net_asset: Munch = None
    tf_folder: str = None
    network_name: str = None
    storage_pool_path: str = None

    def __post_init__(self):
        super().__post_init__()
