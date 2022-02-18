from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

from triggers.env_trigger import DataPool, Triggerable


@dataclass
class BaseConfig(Triggerable, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __post_init__(self):
        """
        Set all variables to their default values
        Assuming key on target dict (where get_default get its values from)
        """
        for k, v in self.get_all().items():
            try:
                if v is None:
                    setattr(self, k, self.get_default(k))
            except AttributeError:
                setattr(self, k, None)

    @abstractmethod
    def _get_data_pool(self) -> DataPool:
        pass

    @classmethod
    def get_annotations(cls):
        """Get attributes with annotations - same as obj.__annotations__ but recursive"""

        annotations = {}
        for c in cls.mro():
            try:
                annotations.update(**c.__annotations__)
            except AttributeError:
                # object, at least, has no __annotations__ attribute.
                pass
        return annotations

    def get_default(self, key, default=None) -> Any:
        global_variables = self._get_data_pool()
        return getattr(global_variables, key, default)

    def get_copy(self):
        return self.__class__(**self.get_all())

    def get_all(self) -> dict:
        return asdict(self)

    def _set(self, key: str, value: Any):
        if hasattr(self, key):
            self.__setattr__(key, value)

    def set_value(self, attr: str, new_val):
        setattr(self, attr, self._get_correct_value(attr, new_val))

    def _get_correct_value(self, attr: str, new_val):
        """Get value in it's correct type"""
        annotations = self.get_annotations()
        if not hasattr(self, attr):
            raise AttributeError(f"Can't find {attr} among {annotations}")

        _type = annotations[attr]

        if hasattr(_type, "__origin__"):
            return _type.__origin__([new_val])

        # str, int, float, bool, Path, and more
        return new_val if isinstance(new_val, _type) else _type(new_val)
