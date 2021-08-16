from abc import ABC

from dataclasses import dataclass

from .base_entity_config import BaseEntityConfig



@dataclass
class BaseInfraEnvConfig(BaseEntityConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during it's execution
    All arguments must have default to None with type hint
    """
    pull_secret: str = None
    ssh_public_key: str = None
    openshift_version: str = None
    infra_env_id: str = None
    infra_env_name: str = None
    additional_ntp_source: str = None
    user_managed_networking: bool = None
    high_availability_mode: str = None
    hyperthreading: str = None
    iso_download_path: str = None  # Todo - Might change during MGMT-5370
    iso_image_type: str = None
    nodes_count: int = None  # Todo - Might change during MGMT-5370
    download_image: bool = None
    platform: str = None
    is_static_ip: bool = None
    is_ipv6: bool = None  # Todo - Might change during MGMT-5370

    def is_cluster(self) -> bool:
        return False

    def is_infra_env(self) -> bool:
        return True
