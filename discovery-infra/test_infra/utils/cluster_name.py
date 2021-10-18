import uuid

from test_infra import consts
from test_infra.utils import get_env


def get_cluster_name_suffix(length: str = consts.SUFFIX_LENGTH):
    return str(uuid.uuid4())[: length]


class ClusterName:
    def __init__(self, prefix: str = None, suffix: str = None):
        self.prefix = prefix if prefix is not None else get_env("CLUSTER_NAME", f"{consts.CLUSTER_PREFIX}")
        self.suffix = suffix if suffix is not None else get_cluster_name_suffix()

    def __str__(self):
        return self.get()

    def __repr__(self):
        return self.get()

    def get(self):
        name = self.prefix
        if self.prefix == consts.CLUSTER_PREFIX and self.suffix:
            name = self.prefix + "-" + self.suffix
        return name
