from abc import ABC
from dataclasses import dataclass

from assisted_test_infra.test_infra.helper_classes.config.controller_config import BaseNodeConfig


@dataclass
class BaseNutanixConfig(BaseNodeConfig, ABC):
    nutanix_username: str = None
    nutanix_password: str = None
    nutanix_endpoint: str = None
    nutanix_port: int = None
    nutanix_cluster: str = None
    nutanix_subnet: str = None
