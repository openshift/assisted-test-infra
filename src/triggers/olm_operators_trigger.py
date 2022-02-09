from contextlib import suppress

from assisted_test_infra.test_infra.utils.operators_utils import resource_param
from consts import OperatorResource
from triggers.env_trigger import Trigger, Triggerable


class OlmOperatorsTrigger(Trigger):
    def __init__(self, condition: str, **kwargs):
        super().__init__(condition, **kwargs)

    def is_condition_met(self, config: Triggerable):
        if hasattr(config, "olm_operators") and self._conditions in getattr(config, "olm_operators", []):
            return True

        return False

    def handle_trigger(self, config: Triggerable):
        variables_to_set = self.get_olm_variables(config)
        config.handle_trigger(self._conditions, variables_to_set)

    def get_olm_variables(self, config: Triggerable) -> dict:
        operator_variables = {}
        operator = self._conditions

        if not isinstance(operator, str):
            return {}

        for key in OperatorResource.get_resource_dict().keys():
            with suppress(AttributeError):
                operator_variables[key] = resource_param(getattr(config, key), key, operator)

        return operator_variables
