from abc import ABC, abstractmethod

from dataclasses import dataclass

from .base_config import _BaseConfig


@dataclass
class BaseEntityConfig(_BaseConfig, ABC):
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
    is_ipv6: bool = None

    @abstractmethod
    def is_cluster(self) -> bool:
        pass

    @abstractmethod
    def is_infra_env(self) -> bool:
        pass
