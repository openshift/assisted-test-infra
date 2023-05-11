from contextlib import suppress
from typing import Callable, List

from assisted_test_infra.test_infra.utils.operators_utils import resource_param
from consts import OperatorResource
from triggers.env_trigger import Trigger, Triggerable


class OlmOperatorsTrigger(Trigger):
    def __init__(self, conditions: List[Callable[[Triggerable], bool]], operator: str, is_sno: bool = False):
        super().__init__(conditions=conditions, operator=operator)
        self._operator = operator
        self._is_sno = is_sno

    def handle(self, config: Triggerable):
        variables_to_set = self.get_olm_variables(config)
        config.handle_trigger(self._conditions_strings, variables_to_set)

    def get_olm_variables(self, config: Triggerable) -> dict:
        operator_variables = {}

        for key in OperatorResource.get_resource_dict().keys():
            with suppress(AttributeError):
                operator_variables[key] = resource_param(getattr(config, key), key, self._operator, self._is_sno)

        return operator_variables
