from abc import ABC, abstractmethod
from typing import Any

from dataclasses import dataclass, asdict


@dataclass
class _BaseConfig(ABC):
    def __post_init__(self):
        """
        Set all variables to its default value
        Assuming key on target dict (where get_default get it's values from)
        """
        for k, v in self.get_all().items():
            if v is None:
                setattr(self, k, self.get_default(k))

    @staticmethod
    @abstractmethod
    def get_default(key, default=None) -> Any:
        pass

    @abstractmethod
    def get_copy(self):
        pass

    def get_all(self) -> dict:
        return asdict(self)
