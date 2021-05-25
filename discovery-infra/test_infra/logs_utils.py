import warnings

from test_infra.utils.logs_utils import *


warnings.filterwarnings("default", category=DeprecationWarning)

deprecation_format = "\033[93mWARNING {name} module will soon be deprecated." \
                     " Avoid adding new functionality to this module. For more information see " \
                     "https://issues.redhat.com/browse/MGMT-4975\033[0m"

warnings.warn("test_infra.log_utils module is deprecated. Use test_infra.utils.log_utils instead.",
              PendingDeprecationWarning)
