from tests.conftest import env_variables


class EnvConfig:
    """
    Forcing the user not to update env_variable
    TODO: this is a temporary class and it will be changed in the next PR
    """
    _config = env_variables

    @classmethod
    def get(cls, key: str, default=None):
        return cls._config.get(key, default)
