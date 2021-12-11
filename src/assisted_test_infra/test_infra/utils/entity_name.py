from assisted_test_infra.test_infra import consts
from assisted_test_infra.test_infra.utils.base_name import BaseName


class ClusterName(BaseName):
    def __init__(self, prefix: str = None, suffix: str = None):
        super().__init__(
            env_var="CLUSTER_NAME",
            default_prefix=consts.CLUSTER_PREFIX,
            prefix=prefix,
            suffix=suffix,
        )


class InfraEnvName(BaseName):
    def __init__(self, prefix: str = None, suffix: str = None):
        super().__init__(
            env_var="INFRA_ENV_NAME",
            default_prefix=consts.INFRA_ENV_PREFIX,
            prefix=prefix,
            suffix=suffix,
        )
