import sys
import warnings
import time

__displayed_warnings = list()


def warn_deprecate():
    if "targets" in sys.argv[0]:
        return
    if sys.argv[0] not in __displayed_warnings:
        if sys.argv[0].endswith("__main__.py"):
            return 
        warnings.filterwarnings("default", category=PendingDeprecationWarning)

        deprecation_format = "\033[93mWARNING {name} module will soon be deprecated." \
                             " Avoid adding new functionality to this module. For more information see " \
                             "https://issues.redhat.com/browse/MGMT-4975\033[0m"

        warnings.warn(deprecation_format.format(name=sys.argv[0]), PendingDeprecationWarning)
        __displayed_warnings.append(sys.argv[0])
        time.sleep(5)
