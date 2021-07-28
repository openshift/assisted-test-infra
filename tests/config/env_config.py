import warnings

from tests.config import global_variables


class EnvConfig:
    """
    TODO: Delete this class after QE will change all og their usages to global_variables
    """

    @classmethod
    def get(cls, key: str, default=None):
        warnings.warn("EnvConfig is deprecated and will be deleted soon."
                      "Use tests.config.global_variables instead", DeprecationWarning)

        try:
            return getattr(global_variables, key)
        except AttributeError:
            return default
