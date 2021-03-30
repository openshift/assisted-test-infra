from tests.conftest import env_variables


DEFAULT_API_VIP = env_variables.get('api_vip', '')
DEFAULT_API_VIP_DNS_NAME = env_variables.get('api_vip_dns_name', '')
DEFAULT_INGRESS_VIP = env_variables.get('ingress_vip', '')

DEFAULT_MACHINE_CIDR = env_variables.get('machine_cidr', '')
DEFAULT_CLUSTER_CIDR = env_variables.get('cluster_cidr', '172.30.0.0/16')
DEFAULT_SERVICE_CIDR = env_variables.get('service_cidr', '10.128.0.0/14')

DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT = 60
DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT = 300
DEFAULT_WAIT_FOR_AGENTS_TIMEOUT = 60
DEFAULT_WAIT_FOR_INSTALLATION_COMPLETE_TIMEOUT = 2 * 60 * 60  # 2 hours
