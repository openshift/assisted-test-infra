import inspect
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from assisted_test_infra.test_infra.utils import EnvVar
from service_client import log


class DataPool(ABC):
    @classmethod
    @abstractmethod
    def get_env(cls, item) -> EnvVar:
        pass


class VariableOrigin(Enum):
    ENVIRONMENT = "ENVIRONMENT"
    PARAMETERIZED = "PARAMETERIZED"
    TRIGGER = "TRIGGER"


class Triggerable(ABC):
    def _is_set(self, var, expected_value):
        return getattr(self._get_data_pool(), var, None) == expected_value

    @abstractmethod
    def _get_data_pool(self) -> DataPool:
        pass

    def get_item_origin(self, item: str) -> Optional[VariableOrigin]:
        try:
            attr = self._get_data_pool().get_env(item)
            return VariableOrigin.ENVIRONMENT if attr.is_user_set else None
        except AttributeError:
            return None

    def handle_trigger(self, conditions_string: List[List[str]], values: Dict[str, Any]) -> None:
        for k, v in values.items():
            if not hasattr(self, k):
                continue

            origin = self.get_item_origin(k)
            # Allow re-set variable that was triggered more than once
            if not origin or origin == VariableOrigin.TRIGGER:
                log.debug(f"{self.__class__.__name__} - Trigger set `{k}` to `{v}`, Condition: {conditions_string}")
                self._set(k, v)
            else:
                log.warning(
                    f"Skipping setting {k} to value {v} due that it already been set by the user ({origin.value})"
                )

    @abstractmethod
    def _set(self, key: str, value: Any):
        pass


class Trigger:
    """Mechanism for applying pre-known configurations if a given trigger condition was met"""

    def __init__(self, *, conditions: List[Callable[[Triggerable], bool]], **kwargs):
        self._conditions = conditions
        self._variables_to_set = kwargs
        conditions_strings = []
        for condition in conditions:
            conditions_strings.append(re.findall(r"(lambda.*),", str(inspect.getsourcelines(condition)[0])))
        self._conditions_strings = conditions_strings

    def is_condition_met(self, configs: List[Triggerable]):
        met = []
        for condition in self._conditions:
            for config in configs:
                try:
                    if condition(config):
                        met.append(True)
                        break
                except AttributeError:
                    pass

        return len(met) > 0 and len(met) == len(self._conditions) and all(met)

    def handle(self, config: Triggerable):
        config.handle_trigger(self._conditions_strings, self._variables_to_set)

    @classmethod
    def trigger_configurations(cls, configs: List[Triggerable], default_triggers: dict):
        met_triggers = {}

        for trigger_name, trigger in default_triggers.items():
            if trigger.is_condition_met(configs):
                met_triggers[trigger_name] = trigger

        for trigger_name, trigger in met_triggers.items():
            for config in configs:
                log.info(f"Handling {trigger_name} trigger")
                trigger.handle(config)
