import pytest
import os
import distutils
from distutils import util

env_variables = {
    "SSH_PUBLIC_KEY": os.environ.get('SSH_PUB_KEY').strip(),
    "REMOTE_SERVICE_URL": os.environ.get('REMOTE_SERVICE_URL').strip(),
    "PULL_SECRET": os.environ.get('PULL_SECRET').strip(),
    "CLUSTER_NAME": os.environ.get('CLUSTER_NAME').strip(),
    "OFFLINE_TOKEN": os.environ.get('OFFLINE_TOKEN').strip(),
    "OPENSHIFT_VERSION": os.environ.get('OPENSHIFT_VERSION').strip(),
    "BASE_DOMAIN": os.environ.get('BASE_DOMAIN').strip(),
    "ISO_DOWNLOAD_PATH": os.environ.get('ISO').strip(),
    "NUM_MASTERS": int(os.environ.get('NUM_MASTERS').strip()),
    "NUM_WORKERS": int(os.environ.get('NUM_WORKERS').strip()),
    "VIP_DHCP_ALLOCATION": bool(util.strtobool(os.environ.get('VIP_DHCP_ALLOCATION')))
}

env_variables["NUM_NODES"] = env_variables["NUM_WORKERS"] + env_variables["NUM_MASTERS"]
