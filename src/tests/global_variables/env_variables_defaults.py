from abc import ABC
from dataclasses import dataclass
from distutils.util import strtobool
from pathlib import Path
from typing import Any, ClassVar

import consts
from assisted_test_infra.test_infra.utils import EnvVar
from consts import env_defaults, resources


@dataclass(frozen=True)
class _EnvVariables(ABC):
    ssh_public_key: EnvVar = EnvVar(["SSH_PUB_KEY"])
    remote_service_url: EnvVar = EnvVar(["REMOTE_SERVICE_URL"])
    pull_secret: EnvVar = EnvVar(["PULL_SECRET"])
    deploy_target: EnvVar = EnvVar(["DEPLOY_TARGET"])
    offline_token: EnvVar = EnvVar(["OFFLINE_TOKEN"])
    openshift_version: EnvVar = EnvVar(["OPENSHIFT_VERSION"], default=consts.OpenshiftVersion.VERSION_4_9)
    base_dns_domain: EnvVar = EnvVar(["BASE_DOMAIN"], default=env_defaults.DEFAULT_BASE_DNS_DOMAIN)
    masters_count: EnvVar = EnvVar(
        ["MASTERS_COUNT", "NUM_MASTERS"], loader=int, default=env_defaults.DEFAULT_NUMBER_OF_MASTERS
    )
    workers_count: EnvVar = EnvVar(
        ["WORKERS_COUNT", "NUM_WORKERS"], loader=int, default=env_defaults.DEFAULT_WORKERS_COUNT
    )
    num_day2_workers: EnvVar = EnvVar(["NUM_DAY2_WORKERS"], loader=int, default=env_defaults.DEFAULT_DAY2_WORKERS_COUNT)
    vip_dhcp_allocation: EnvVar = EnvVar(
        ["VIP_DHCP_ALLOCATION"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_VIP_DHCP_ALLOCATION
    )

    worker_memory: EnvVar = EnvVar(["WORKER_MEMORY"], loader=int, default=resources.DEFAULT_WORKER_MEMORY)
    master_memory: EnvVar = EnvVar(["MASTER_MEMORY"], loader=int, default=resources.DEFAULT_MASTER_MEMORY)
    network_mtu: EnvVar = EnvVar(["NETWORK_MTU"], loader=int, default=resources.DEFAULT_MTU)
    worker_disk: EnvVar = EnvVar(["WORKER_DISK"], loader=int, default=resources.DEFAULT_WORKER_DISK)
    master_disk: EnvVar = EnvVar(["MASTER_DISK"], loader=int, default=resources.DEFAULT_MASTER_DISK)
    master_disk_count: EnvVar = EnvVar(["MASTER_DISK_COUNT"], loader=int, default=resources.DEFAULT_DISK_COUNT)
    worker_disk_count: EnvVar = EnvVar(["WORKER_DISK_COUNT"], loader=int, default=resources.DEFAULT_DISK_COUNT)
    storage_pool_path: EnvVar = EnvVar(["STORAGE_POOL_PATH"], default=env_defaults.DEFAULT_STORAGE_POOL_PATH)
    private_ssh_key_path: EnvVar = EnvVar(
        ["PRIVATE_KEY_PATH"], loader=Path, default=env_defaults.DEFAULT_SSH_PRIVATE_KEY_PATH
    )
    installer_kubeconfig_path: EnvVar = EnvVar(
        ["INSTALLER_KUBECONFIG"], default=env_defaults.DEFAULT_INSTALLER_KUBECONFIG
    )
    log_folder: EnvVar = EnvVar(["LOG_FOLDER"], default=env_defaults.DEFAULT_LOG_FOLDER)
    is_static_ip: EnvVar = EnvVar(
        ["STATIC_IPS"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_STATIC_IPS
    )
    iso_image_type: EnvVar = EnvVar(["ISO_IMAGE_TYPE"], default=env_defaults.DEFAULT_IMAGE_TYPE)
    worker_vcpu: EnvVar = EnvVar(["WORKER_CPU"], loader=int, default=resources.DEFAULT_WORKER_CPU)
    master_vcpu: EnvVar = EnvVar(["MASTER_CPU"], loader=int, default=resources.DEFAULT_MASTER_CPU)
    test_teardown: EnvVar = EnvVar(
        ["TEST_TEARDOWN"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_TEST_TEARDOWN
    )

    namespace: EnvVar = EnvVar(["NAMESPACE"], default=consts.DEFAULT_NAMESPACE)
    olm_operators: EnvVar = EnvVar(["OLM_OPERATORS"], loader=lambda operators: operators.lower().split(), default="")
    platform: EnvVar = EnvVar(["PLATFORM"], default=env_defaults.DEFAULT_PLATFORM)
    user_managed_networking: EnvVar = EnvVar(default=env_defaults.DEFAULT_USER_MANAGED_NETWORKING)
    high_availability_mode: EnvVar = EnvVar(default=env_defaults.DEFAULT_HIGH_AVAILABILITY_MODE)
    download_image: EnvVar = EnvVar(
        ["DOWNLOAD_IMAGE"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_DOWNLOAD_IMAGE
    )
    verify_download_iso_ssl: EnvVar = EnvVar(
        ["VERIFY_DOWNLOAD_ISO_SSL"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_VERIFY_SSL
    )
    is_ipv4: EnvVar = EnvVar(["IPv4"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_IS_IPV4)
    is_ipv6: EnvVar = EnvVar(["IPv6"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_IS_IPV6)
    cluster_id: EnvVar = EnvVar(["CLUSTER_ID"])
    additional_ntp_source: EnvVar = EnvVar(
        ["ADDITIONAL_NTP_SOURCE"], default=env_defaults.DEFAULT_ADDITIONAL_NTP_SOURCE
    )
    network_name: EnvVar = EnvVar(["NETWORK_NAME"], default=env_defaults.DEFAULT_NETWORK_NAME)
    bootstrap_in_place: EnvVar = EnvVar(
        ["BOOTSTRAP_IN_PLACE"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_BOOTSTRAP_IN_PLACE
    )

    single_node_ip: EnvVar = EnvVar(["SINGLE_NODE_IP"], default=env_defaults.DEFAULT_SINGLE_NODE_IP)
    worker_cpu_mode: EnvVar = EnvVar(["WORKER_CPU_MODE"], default=env_defaults.DEFAULT_TF_CPU_MODE)
    master_cpu_mode: EnvVar = EnvVar(["MASTER_CPU_MODE"], default=env_defaults.DEFAULT_TF_CPU_MODE)
    iso_download_path: EnvVar = EnvVar(["ISO_DOWNLOAD_PATH", "ISO"])  # todo replace ISO env var->ISO_DOWNLOAD_PATH
    hyperthreading: EnvVar = EnvVar(["HYPERTHREADING"])
    network_type: EnvVar = EnvVar(["NETWORK_TYPE"], default=env_defaults.DEFAULT_NETWORK_TYPE)
    disk_encryption_mode: EnvVar = EnvVar(["DISK_ENCRYPTION_MODE"], default=env_defaults.DEFAULT_DISK_ENCRYPTION_MODE)
    disk_encryption_roles: EnvVar = EnvVar(
        ["DISK_ENCRYPTION_ROLES"], default=env_defaults.DEFAULT_DISK_ENCRYPTION_ROLES
    )
    is_kube_api: EnvVar = EnvVar(
        ["KUBE_API"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_IS_KUBE_API
    )

    vsphere_cluster: EnvVar = EnvVar(["VSPHERE_CLUSTER"])
    vsphere_username: EnvVar = EnvVar(["VSPHERE_USERNAME"])
    vsphere_password: EnvVar = EnvVar(["VSPHERE_PASSWORD"])
    vsphere_network: EnvVar = EnvVar(["VSPHERE_NETWORK"])
    vsphere_vcenter: EnvVar = EnvVar(["VSPHERE_VCENTER"])
    vsphere_datacenter: EnvVar = EnvVar(["VSPHERE_DATACENTER"])
    vsphere_datastore: EnvVar = EnvVar(["VSPHERE_DATASTORE"])


@dataclass(frozen=True)
class _EnvVariablesDefaults(_EnvVariables, ABC):
    __instance: ClassVar = None

    @property
    def nodes_count(self):
        return (self.masters_count + self.workers_count).get()

    def get_env(self, item: str) -> EnvVar:
        return super().__getattribute__(item)

    def __getattribute__(self, item):
        attr = super().__getattribute__(item)
        if isinstance(attr, EnvVar):
            return attr.get()
        return attr

    def __new__(cls, *args, **kwargs):
        """Prevent creating another env_var instance"""
        if isinstance(cls.__instance, cls):
            raise Exception("Can't initialized more then one global configuration object")
        cls.__instance = object.__new__(cls, *args, **kwargs)
        return cls.__instance

    def _set(self, key: str, value: Any):
        if not hasattr(self, key):
            raise AttributeError(f"Invalid key {key}")

        super().__setattr__(key, value)
