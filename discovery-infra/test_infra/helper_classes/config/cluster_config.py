from abc import ABC
from typing import List

from dataclasses import dataclass

from .base_entity_config import BaseEntityConfig

from test_infra.utils.entity_name import ClusterName


@dataclass
class BaseClusterConfig(BaseEntityConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during it's execution
    All arguments must have default to None with type hint
    """
    cluster_id: str = None
    cluster_name: ClusterName = None
    olm_operators: List[str] = None
    vip_dhcp_allocation: bool = None
    service_network_cidr: str = None
    cluster_network_cidr: str = None
    cluster_network_host_prefix: int = None
    kubeconfig_path: str = None
    network_type: str = None
