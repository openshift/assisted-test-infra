from abc import ABC
from dataclasses import dataclass

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
    high_availability_mode: str = None
    hyperthreading: str = None
    iso_download_path: str = None
    iso_image_type: str = None
    download_image: bool = None
    platform: str = None
    is_static_ip: bool = None
    is_ipv4: bool = None
    is_ipv6: bool = None
    base_dns_domain: str = None
    entity_name: BaseName = None
    proxy: models.Proxy = None
