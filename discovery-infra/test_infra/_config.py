from tests.conftest import env_variables


class Config:
    """
    Forcing the user not to update env_variable
    TODO: this is a temporary class and it will be changed in the next PR
    """
    __config = env_variables

    @classmethod
    def get(cls, key: str, default=None):
        # return cls.__config.get(key, default=default)
        return cls.__config[key]

    @classmethod
    def get_group(cls, *args) -> dict:
        variables = dict()
        for k in args:
            variables[k] = cls.get(k)
        return variables
