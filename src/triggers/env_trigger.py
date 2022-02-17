from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Union

from assisted_test_infra.test_infra.utils import EnvVar
from service_client import log


class DataPool(ABC):
    @classmethod
    @abstractmethod
    def get_env(cls, item) -> EnvVar:
        pass


class Triggerable(ABC):
    def _is_set(self, var, expected_value):
        return getattr(self._get_data_pool(), var, None) == expected_value

    @abstractmethod
    def _get_data_pool(self) -> DataPool:
        pass

    def is_user_set(self, item: str):
        try:
            attr = self._get_data_pool().get_env(item)
            return attr.is_user_set
        except AttributeError:
            return False

    def handle_trigger(self, cond: Union[Tuple[str, Any], Tuple[Tuple[str, Any]]], values: Dict[str, Any]) -> None:
        for k, v in values.items():
            if not hasattr(self, k):
                continue

            if not self.is_user_set(k):
                log.debug(f"{self.__class__.__name__} - Trigger set {k} to {v}, Condition: {cond}")
                self._set(k, v)
            else:
                log.warning(f"Skipping setting {k} to value {v} due that it already been set by the user")

    @abstractmethod
    def _set(self, key: str, value: Any):
        pass


class Trigger:
    """Mechanism for applying pre-known configurations if a given trigger condition was met"""

    def __init__(self, condition: Union[Tuple[str, Any], Tuple[Tuple[str, Any], Tuple[str, Any]]], **kwargs):
        self._conditions = condition
        self._variables_to_set = kwargs

    def is_condition_met(self, config: Triggerable):
        conditions = self._conditions
        if not isinstance(conditions[0], tuple):
            conditions = (conditions,)
        return all(self._is_set(config, param, expected_value) for param, expected_value in conditions)

    def handle_trigger(self, config: Triggerable):
        config.handle_trigger(self._conditions, self._variables_to_set)

    @classmethod
    def _is_set(cls, config, var, expected_value):
        return getattr(config, var, None) == expected_value

    @classmethod
    def trigger_configurations(cls, configs: List[Triggerable], default_triggers: dict):
        met_triggers = {}

        for trigger_name, trigger in default_triggers.items():
            for config in configs:
                if trigger.is_condition_met(config):
                    met_triggers[trigger_name] = trigger
                    break

        for trigger_name, trigger in met_triggers.items():
            for config in configs:
                log.info(f"Handling {trigger_name} trigger")
                trigger.handle_trigger(config)
