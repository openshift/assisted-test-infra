from typing import Any, Callable, List, Optional

from assisted_test_infra.test_infra.utils.utils import get_env


class EnvVar:
    def __init__(
        self, var_keys: List[str] = None, *, loader: Optional[Callable] = None, default: Optional[Any] = None
    ) -> None:
        self.__var_keys = var_keys if var_keys else []
        self.__loader = loader
        self.__default = default
        self.__is_user_set = False
        self.__value = None
        self.__cached = None
        self.get()

    def __getattribute__(self, name: str) -> Any:
        try:
            return super().__getattribute__(name)
        except AttributeError:
            return self.__value.__getattribute__(name)

    def __add__(self, other: "EnvVar"):
        return EnvVar(default=self.get() + other.get())

    def __str__(self):
        return str(self.__value)

    @property
    def is_user_set(self):
        return self.__is_user_set

    def get(self, reload: bool = False):
        # Try to load from cache
        if self.__cached and not reload:
            return self.__value

        self.__cached = True

        value = self.__default
        for key in self.__var_keys:
            env = get_env(key)
            if env is not None:
                self.__is_user_set = True
                value = self.__loader(env) if self.__loader else env
                break
        self.__value = value
        return value
