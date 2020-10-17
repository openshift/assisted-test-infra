import pytest
import os
from distutils import util

env_variables = {
    "SSH_PUBLIC_KEY": os.environ.get('SSH_PUB_KEY'),
    "REMOTE_SERVICE_URL": os.environ.get('REMOTE_SERVICE_URL'),
    "PULL_SECRET": os.environ.get('PULL_SECRET'),
    "CLUSTER_NAME": os.environ.get('CLUSTER_NAME'),
    "OFFLINE_TOKEN": os.environ.get('OFFLINE_TOKEN'),
    "OPENSHIFT_VERSION": os.environ.get('OPENSHIFT_VERSION'),
    "BASE_DOMAIN": os.environ.get('BASE_DOMAIN'),
    "ISO_DOWNLOAD_PATH": os.environ.get('ISO'),
    "NUM_MASTERS": int(os.environ.get('NUM_MASTERS')),
    "NUM_WORKERS": int(os.environ.get('NUM_WORKERS')),
    "VIP_DHCP_ALLOCATION": bool(util.strtobool(os.environ.get('VIP_DHCP_ALLOCATION'))),
    "HTTP_PROXY": os.environ.get('HTTP_PROXY'),
    "KUBECONFIG_PATH": os.environ.get('KUBECONFIG')
}

env_variables["NUM_NODES"] = env_variables["NUM_WORKERS"] + env_variables["NUM_MASTERS"]
