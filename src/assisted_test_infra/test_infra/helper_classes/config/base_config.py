from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from types import NoneType
from typing import Any, Union, get_args, get_origin

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
        # store all keys called from update_parameterized from base_test
        # default trigger will skip updated params from pytest.mark.parametrize
        self.update_parameterized_keys = set()

    @abstractmethod
    def _get_data_pool(self) -> DataPool:
        pass

    def is_user_set(self, item: str):
        # Check if the item already set by user
        return item in self.update_parameterized_keys

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

    def set_value(self, attr: str, new_val, update_parameterized=False):
        setattr(self, attr, self._get_correct_value(attr, new_val))
        if update_parameterized:
            self.update_parameterized_keys.add(attr)

    @classmethod
    def _get_annotations_actual_type(cls, annotations: dict, key: str) -> Any:
        _type = annotations[key]

        if get_origin(_type) is not Union:
            return _type

        # Optional is actually a Union[<type>, NoneType]
        _args = get_args(_type)
        if len(_args) > 1 and _args[1] is NoneType:
            return _args[0]

        raise ValueError(f"Type {_type} is not supported in {cls.__name__}")

    def _get_correct_value(self, attr: str, new_val):
        """Get value in its correct type"""
        annotations = self.get_annotations()
        if not hasattr(self, attr):
            raise AttributeError(f"Can't find {attr} among {annotations}")

        _type = self._get_annotations_actual_type(annotations, attr)

        if hasattr(_type, "__origin__"):
            return _type.__origin__(new_val)

        # str, int, float, bool, Path, and more
        return new_val if isinstance(new_val, _type) else _type(new_val)
