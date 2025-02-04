from abc import ABC
from dataclasses import dataclass
from typing import Optional

from assisted_service_client import models

from ...utils.base_name import BaseName
from .base_config import BaseConfig


@dataclass
class BaseEntityConfig(BaseConfig, ABC):
    pull_secret: str = None
    ssh_public_key: str = None
    openshift_version: str = None
    additional_ntp_source: str = None
    user_managed_networking: bool = None
    control_plane_count: str = None
    hyperthreading: str = None
    iso_download_path: str = None  # TODO Needed only on infra env. Remove from here and move to BaseInfraEnvConfig
    worker_iso_download_path: str = None
    iso_image_type: str = None
    download_image: bool = None
    platform: str = None
    external_platform_name: str = None
    external_cloud_controller_manager: str = None
    is_ipv4: bool = None
    is_ipv6: bool = None
    base_dns_domain: str = None
    entity_name: BaseName = None
    proxy: models.Proxy = None
    ipxe_boot: bool = None
    cpu_architecture: Optional[str] = None
    is_bonded: bool = None
    num_bonded_slaves: int = None
    bonding_mode: str = None
    cluster_id: str = None
    load_balancer_type: str = None
