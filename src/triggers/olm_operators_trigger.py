from contextlib import suppress
from typing import Callable

from assisted_test_infra.test_infra.utils.operators_utils import resource_param
from consts import OperatorResource
from triggers.env_trigger import Trigger, Triggerable


class OlmOperatorsTrigger(Trigger):
    def __init__(self, condition: Callable[[Triggerable], bool], operator: str):
        super().__init__(condition=condition, operator=operator)
        self._operator = operator

    def handle(self, config: Triggerable):
        variables_to_set = self.get_olm_variables(config)
        config.handle_trigger(self._conditions_string, variables_to_set)

    def get_olm_variables(self, config: Triggerable) -> dict:
        operator_variables = {}

        for key in OperatorResource.get_resource_dict().keys():
            with suppress(AttributeError):
                operator_variables[key] = resource_param(getattr(config, key), key, self._operator)

        return operator_variables
