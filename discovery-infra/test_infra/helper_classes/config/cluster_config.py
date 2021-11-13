from abc import ABC
from dataclasses import dataclass
from typing import List

from assisted_service_client import models
from test_infra.utils.entity_name import ClusterName

from .base_entity_config import BaseEntityConfig


@dataclass
class BaseClusterConfig(BaseEntityConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during its execution.
    All arguments must default to None and be type annotated.
    """

    cluster_id: str = None
    cluster_name: ClusterName = None
    olm_operators: List[str] = None
    vip_dhcp_allocation: bool = None
    cluster_networks: List[models.ClusterNetwork] = None
    service_networks: List[models.ServiceNetwork] = None
    kubeconfig_path: str = None
    network_type: str = None
    disk_encryption_mode: str = None
    disk_encryption_roles: str = None
