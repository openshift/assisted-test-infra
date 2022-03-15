from typing import Any, Callable, List, Optional

from assisted_test_infra.test_infra.utils.utils import get_env


class EnvVar:
    """
    Get env vars from os environment variables while saving the source of the data
    Attributes:
        __var_keys      Environment variables keys as passed to test_infra, if multiple keys are set, taking the first
        __loader        Function to execute on the env var when getting it from system
        __default       Default value for variable if not set
        __is_user_set   Set to true if one of the environment variables in __var_keys was set by the user
        __value         The actual calculated value of the variable (user -> default)
        __cached        Set to True when first time setting __value, prevent reloading the value each time it's
                        being accessed
    """

    def __init__(
        self, var_keys: List[str] = None, *, loader: Optional[Callable] = None, default: Optional[Any] = None
    ) -> None:
        self.__var_keys = var_keys if var_keys else []
        self.__loader = loader
        self.__default = default
        self.__is_user_set = False
        self.__value = self.value

    def __getattr__(self, item: str):
        return self.__value.__getattribute__(item)

    def __add__(self, other: "EnvVar"):
        return EnvVar(default=self.get() + other.get())

    def __str__(self):
        return f"{f'{self.__var_keys[0]}=' if len(self.__var_keys) > 0 else ''}{self.__value}"

    @property
    def var_keys(self):
        return self.__var_keys

    @property
    def is_user_set(self):
        return self.__is_user_set

    @property
    def value(self):
        value = self.__default
        for key in self.__var_keys:
            env = get_env(key)
            if env is not None:
                self.__is_user_set = True
                value = self.__loader(env) if self.__loader else env
                break
        return value
