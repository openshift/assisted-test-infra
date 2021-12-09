import sys
import time
import warnings

__displayed_warnings = list()


def warn_deprecate():
    if sys.argv[0] not in __displayed_warnings:
        if sys.argv[0].endswith("__main__.py"):
            return
        warnings.filterwarnings("default", category=PendingDeprecationWarning)

        deprecation_format = (
            f"\033[93mWARNING {sys.argv[0]} module will soon be deprecated."
            " Avoid adding new functionality to this module. For more information see "
            "https://issues.redhat.com/browse/MGMT-4975\033[0m"
        )

        warnings.warn(deprecation_format, PendingDeprecationWarning)
        __displayed_warnings.append(sys.argv[0])
        time.sleep(5)
