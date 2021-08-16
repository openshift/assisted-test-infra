from test_infra.utils.base_name import BaseName
from test_infra import consts


class InfraEnvName(BaseName):
    def __init__(self, prefix: str = None, suffix: str = None):
        super(InfraEnvName, self).__init__("INFRA_ENV_NAME", consts.INFRA_ENV_PREFIX, prefix=prefix, suffix=suffix)
