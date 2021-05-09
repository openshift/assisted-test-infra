from tests.conftest import env_variables

# TODO - Temporary import - for backward compatibility
from test_infra.consts.kube_api import *

# TODO - remove all env variables dependency
DEFAULT_API_VIP = env_variables.get('api_vip', '')
DEFAULT_API_VIP_DNS_NAME = env_variables.get('api_vip_dns_name', '')
DEFAULT_INGRESS_VIP = env_variables.get('ingress_vip', '')

DEFAULT_MACHINE_CIDR = env_variables.get('machine_cidr', '')
DEFAULT_CLUSTER_CIDR = env_variables.get('cluster_cidr', '172.30.0.0/16')
DEFAULT_SERVICE_CIDR = env_variables.get('service_cidr', '10.128.0.0/14')
