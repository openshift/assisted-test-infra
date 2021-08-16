from test_infra.utils.base_name import BaseName
from test_infra import consts


class ClusterName(BaseName):
    def __init__(self, prefix: str = None, suffix: str = None):
        super(ClusterName, self).__init__("CLUSTER_NAME", consts.CLUSTER_PREFIX, prefix=prefix, suffix=suffix)
