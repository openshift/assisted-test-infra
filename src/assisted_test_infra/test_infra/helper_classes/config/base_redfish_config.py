from abc import ABC
from dataclasses import dataclass
from typing import List

from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig


@dataclass
class BaseRedfishConfig(BaseNodesConfig, ABC):
    redfish_user: str = None
    redfish_password: str = None
    redfish_machines: List[str] = None
    redfish_enabled: bool = False
