import uuid

from test_infra import consts
from test_infra.utils import get_env


def get_name_suffix(length: str = consts.SUFFIX_LENGTH):
    return str(uuid.uuid4())[: length]


class BaseName:
    def __init__(self, env_var: str, default_prefix: str, prefix: str = None, suffix: str = None):
        self._default_prefix = default_prefix
        self.prefix = prefix if prefix is not None else get_env(env_var, default_prefix)
        self.suffix = suffix if suffix is not None else get_name_suffix()

    def __str__(self):
        return self.get()

    def __repr__(self):
        return self.get()

    def get(self):
        name = self.prefix
        if self.prefix == self._default_prefix and self.suffix:
            name = self.prefix + "-" + self.suffix
        return name
