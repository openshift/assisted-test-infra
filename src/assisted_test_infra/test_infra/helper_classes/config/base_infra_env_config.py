from abc import ABC
from dataclasses import dataclass
from typing import List

from .base_entity_config import BaseEntityConfig


@dataclass
class BaseInfraEnvConfig(BaseEntityConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during it's execution
    All arguments must have default to None with type hint
    """

    infra_env_id: str = None
    static_network_config: List[dict] = None
    ignition_config_override: str = None
    verify_download_iso_ssl: bool = None
    is_static_ip: bool = None
    kernel_arguments: List[dict[str, str]] = None
    host_installer_args: List[dict[str, str]] = None
    set_infraenv_version: bool = None
