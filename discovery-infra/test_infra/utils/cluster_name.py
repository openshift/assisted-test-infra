import uuid

from dataclasses import dataclass

from test_infra import consts
from test_infra.utils import get_env


@dataclass
class ClusterName:
    suffix: str = str(uuid.uuid4())[: consts.SUFFIX_LENGTH]
    prefix: str = get_env("CLUSTER_NAME", f"{consts.CLUSTER_PREFIX}")

    def __str__(self):
        return self.get()

    def __repr__(self):
        return self.get()

    def get(self):
        name = self.suffix
        if self.prefix == consts.CLUSTER_PREFIX:
            name = self.prefix + "-" + self.suffix
        return name
