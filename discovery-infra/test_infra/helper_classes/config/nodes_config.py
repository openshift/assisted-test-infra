from abc import ABC
from typing import List, Any

from dataclasses import dataclass

from .base_config import _BaseConfig


@dataclass
class BaseNodesConfig(_BaseConfig, ABC):
    """
    Define all configurations variables that are needed for Cluster during it's execution
    All arguments must have default to None with type hint
    TODO: Placeholder for NodesConfig to configure NodesControllers Will be implemented in the next PR
    """
