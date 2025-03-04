from abc import ABC
from dataclasses import dataclass
from typing import List

from assisted_service_client import models

from ...utils.entity_name import BaseName, ClusterName
from ...utils.manifests import Manifest
from .base_entity_config import BaseEntityConfig


@dataclass
class BaseClusterConfig(BaseEntityConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during its execution.
    All arguments must default to None and be type annotated.
    """

    cluster_tags: str = None
    olm_operators: List[str] = None
    vip_dhcp_allocation: bool = None
    cluster_networks: List[models.ClusterNetwork] = None
    service_networks: List[models.ServiceNetwork] = None
    machine_networks: List[models.MachineNetwork] = None
    kubeconfig_path: str = None
    network_type: str = None
    api_vips: List[models.ApiVip] = None
    ingress_vips: List[models.IngressVip] = None
    metallb_api_ip: str = None
    metallb_ingress_ip: str = None
    disk_encryption_mode: str = None
    disk_encryption_roles: str = None
    tang_servers: str = None
    custom_manifests: List[Manifest] = None
    is_disconnected: bool = None
    registry_ca_path: str = None
    load_balancer_type: str = None
    load_balancer_cidr: str = None
    install_working_dir: str = None
    libvirt_uri: str = None

    @property
    def cluster_name(self) -> BaseName:
        return self.entity_name

    @cluster_name.setter
    def cluster_name(self, cluster_name: BaseName):
        self.entity_name = cluster_name


# Add cluster_name to __annotations__ dict so we will be able to set it also on get_annotations
# under BaseConfig
BaseClusterConfig.__annotations__["cluster_name"] = ClusterName
