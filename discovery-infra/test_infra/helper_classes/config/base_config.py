from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

from test_infra.utils.global_variables.triggerable import Triggerable


@dataclass
class _BaseConfig(Triggerable, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

    def get_copy(self):
        return self.__class__(**self.get_all())

    def get_all(self) -> dict:
        return asdict(self)

    def _set(self, key: str, value: Any):
        if hasattr(self, key):
            self.__setattr__(key, value)
