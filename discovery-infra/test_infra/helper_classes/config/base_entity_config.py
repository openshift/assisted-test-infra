from abc import ABC, abstractmethod

from dataclasses import dataclass

from .base_config import _BaseConfig


@dataclass
class BaseEntityConfig(_BaseConfig, ABC):

    @abstractmethod
    def is_cluster(self) -> bool:
        pass

    @abstractmethod
    def is_infra_env(self) -> bool:
        pass
