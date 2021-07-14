from abc import ABC
from distutils.util import strtobool
from pathlib import Path
from typing import Any, List

from dataclasses import dataclass, field

from test_infra import consts
from test_infra.consts import env_defaults, resources
from test_infra.utils import get_env, get_openshift_version, operators_utils


@dataclass(frozen=True)
class _EnvVariablesUtils(ABC):
    ssh_public_key: str = get_env("SSH_PUB_KEY")
    remote_service_url: str = get_env("REMOTE_SERVICE_URL")
    pull_secret: str = get_env("PULL_SECRET")
    offline_token: str = get_env("OFFLINE_TOKEN")
    openshift_version: str = get_openshift_version()
    base_dns_domain: str = get_env("BASE_DOMAIN", consts.DEFAULT_BASE_DNS_DOMAIN)
    masters_count: int = int(get_env("MASTERS_COUNT", get_env("NUM_MASTERS", env_defaults.DEFAULT_NUMBER_OF_MASTERS)))
    workers_count: int = int(get_env("WORKERS_COUNT", get_env("NUM_WORKERS", env_defaults.DEFAULT_WORKERS_COUNT)))
    nodes_count: int = masters_count + workers_count
    num_day2_workers: int = int(get_env("NUM_DAY2_WORKERS", env_defaults.DEFAULT_DAY2_WORKERS_COUNT))
    vip_dhcp_allocation: bool = bool(strtobool(get_env("VIP_DHCP_ALLOCATION")))
    worker_memory: int = int(get_env("WORKER_MEMORY", resources.DEFAULT_WORKER_MEMORY))
    master_memory: int = int(get_env("MASTER_MEMORY", resources.DEFAULT_MASTER_MEMORY))
    network_mtu: int = int(get_env("NETWORK_MTU", resources.DEFAULT_MTU))
    worker_disk: int = int(get_env("WORKER_DISK", resources.DEFAULT_WORKER_DISK))
    master_disk: int = int(get_env("MASTER_DISK", resources.DEFAULT_MASTER_DISK))
    master_disk_count: int = int(get_env("MASTER_DISK_COUNT", resources.DEFAULT_DISK_COUNT))
    worker_disk_count: int = int(get_env("WORKER_DISK_COUNT", resources.DEFAULT_DISK_COUNT))
    storage_pool_path: str = get_env("STORAGE_POOL_PATH", env_defaults.DEFAULT_STORAGE_POOL_PATH)
    private_ssh_key_path: Path = Path(get_env("PRIVATE_KEY_PATH", env_defaults.DEFAULT_SSH_PRIVATE_KEY_PATH))
    installer_kubeconfig_path: str = get_env("INSTALLER_KUBECONFIG", env_defaults.DEFAULT_INSTALLER_KUBECONFIG)
    log_folder: str = get_env("LOG_FOLDER", env_defaults.DEFAULT_LOG_FOLDER)
    service_network_cidr: str = get_env("SERVICE_CIDR", env_defaults.DEFAULT_SERVICE_CIDR)
    cluster_network_cidr: str = get_env("CLUSTER_CIDR", env_defaults.DEFAULT_CLUSTER_CIDR)
    cluster_network_host_prefix: int = int(get_env("HOST_PREFIX", env_defaults.DEFAULT_HOST_PREFIX))
    is_static_ip: bool = bool(strtobool(get_env("IS_STATIC_IP", default=str(env_defaults.DEFAULT_IS_STATIC_IP))))
    iso_image_type: str = get_env("ISO_IMAGE_TYPE", env_defaults.DEFAULT_IMAGE_TYPE)
    worker_vcpu: str = get_env("WORKER_CPU", resources.DEFAULT_WORKER_CPU)
    master_vcpu: str = get_env("MASTER_CPU", resources.DEFAULT_MASTER_CPU)
    test_teardown: bool = bool(strtobool(get_env("TEST_TEARDOWN", str(env_defaults.DEFAULT_TEST_TEARDOWN))))
    namespace: str = get_env("NAMESPACE", consts.DEFAULT_NAMESPACE)
    olm_operators: List[str] = field(default_factory=list)
    platform: str = get_env("PLATFORM", env_defaults.DEFAULT_PLATFORM)
    user_managed_networking: bool = env_defaults.DEFAULT_USER_MANAGED_NETWORKING
    high_availability_mode: str = env_defaults.DEFAULT_HIGH_AVAILABILITY_MODE
    download_image: bool = bool(strtobool(get_env("DOWNLOAD_IMAGE", str(env_defaults.DEFAULT_DOWNLOAD_IMAGE))))
    is_ipv6: bool = bool(strtobool(get_env("IS_IPV6", get_env("IPv6", str(env_defaults.DEFAULT_IS_IPV6)))))
    cluster_id: str = get_env("CLUSTER_ID")
    additional_ntp_source: str = get_env("ADDITIONAL_NTP_SOURCE", env_defaults.DEFAULT_ADDITIONAL_NTP_SOURCE)
    network_name: str = get_env("NETWORK_NAME", env_defaults.DEFAULT_NETWORK_NAME)
    bootstrap_in_place: bool = bool(
        strtobool(get_env("BOOTSTRAP_IN_PLACE", str(env_defaults.DEFAULT_BOOTSTRAP_IN_PLACE)))
    )
    single_node_ip: str = get_env("SINGLE_NODE_IP", env_defaults.DEFAULT_SINGLE_NODE_IP)
    worker_cpu_mode: str = get_env("WORKER_CPU_MODE", env_defaults.DEFAULT_TF_CPU_MODE)
    master_cpu_mode: str = get_env("MASTER_CPU_MODE", env_defaults.DEFAULT_TF_CPU_MODE)
    iso_download_path: str = get_env("ISO_DOWNLOAD_PATH", get_env("ISO"))  # todo replace ISO env var->ISO_DOWNLOAD_PATH
    hyperthreading: str = get_env("HYPERTHREADING")

    vsphere_cluster: str = get_env("VSPHERE_CLUSTER")
    vsphere_username: str = get_env("VSPHERE_USERNAME")
    vsphere_password: str = get_env("VSPHERE_PASSWORD")
    vsphere_network: str = get_env("VSPHERE_NETWORK")
    vsphere_vcenter: str = get_env("VSPHERE_VCENTER")
    vsphere_datacenter: str = get_env("VSPHERE_DATACENTER")
    vsphere_datastore: str = get_env("VSPHERE_DATASTORE")

    def __post_init__(self):
        self._set("olm_operators", operators_utils.parse_olm_operators_from_env())

    def _set(self, key: str, value: Any):
        if not hasattr(self, key):
            raise AttributeError(f"Invalid key {key}")

        super().__setattr__(key, value)
