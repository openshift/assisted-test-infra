from dataclasses import dataclass
from typing import List

from .base_entity_config import BaseEntityConfig


@dataclass
class BaseInfraEnvConfig(BaseEntityConfig):
    """
    Define all configurations variables that are needed for Cluster during it's execution
    All arguments must have default to None with type hint
    """

    infra_env_id: str = None
    cluster_id: str = None
    static_network_config: List[dict] = None
    ignition_config_override: str = None
    verify_download_iso_ssl: bool = None
    is_static_ip: bool = None
