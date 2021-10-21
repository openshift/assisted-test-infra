from abc import ABC
from dataclasses import dataclass
from typing import List

from assisted_service_client import models
from test_infra.utils.entity_name import ClusterName

from .base_entity_config import BaseEntityConfig


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
    cluster_networks: List[models.ClusterNetwork] = None
    service_networks: List[models.ServiceNetwork] = None
    kubeconfig_path: str = None
    network_type: str = None
