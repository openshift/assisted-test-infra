import json
import re
from abc import ABC
from dataclasses import dataclass
from distutils.util import strtobool
from pathlib import Path

import consts
from assisted_test_infra.test_infra.utils.env_var import EnvVar
from assisted_test_infra.test_infra.utils.manifests import Manifest
from consts import env_defaults, resources
from triggers.env_trigger import DataPool


@dataclass(frozen=True)
class _EnvVariables(DataPool, ABC):
    ssh_public_key: EnvVar = EnvVar(["SSH_PUB_KEY"])
    remote_service_url: EnvVar = EnvVar(["REMOTE_SERVICE_URL"])
    pull_secret: EnvVar = EnvVar(["PULL_SECRET"])
    deploy_target: EnvVar = EnvVar(["DEPLOY_TARGET"])
    offline_token: EnvVar = EnvVar(["OFFLINE_TOKEN"])
    kernel_arguments: EnvVar = EnvVar(["KERNEL_ARGUMENTS"], loader=json.loads)
    openshift_version: EnvVar = EnvVar(["OPENSHIFT_VERSION"], default=consts.OpenshiftVersion.DEFAULT.value)
    base_dns_domain: EnvVar = EnvVar(["BASE_DOMAIN"], default=env_defaults.DEFAULT_BASE_DNS_DOMAIN)
    cluster_name: EnvVar = EnvVar(["CLUSTER_NAME"], default="")
    cluster_tags: EnvVar = EnvVar(["CLUSTER_TAGS"], default="")
    masters_count: EnvVar = EnvVar(
        ["MASTERS_COUNT", "NUM_MASTERS"], loader=int, default=env_defaults.DEFAULT_NUMBER_OF_MASTERS
    )
    workers_count: EnvVar = EnvVar(
        ["WORKERS_COUNT", "NUM_WORKERS"], loader=int, default=env_defaults.DEFAULT_WORKERS_COUNT
    )
    day2_workers_count: EnvVar = EnvVar(
        ["NUM_DAY2_WORKERS"], loader=int, default=env_defaults.DEFAULT_DAY2_WORKERS_COUNT
    )
    day2_masters_count: EnvVar = EnvVar(
        ["NUM_DAY2_MASTERS"], loader=int, default=env_defaults.DEFAULT_DAY2_MASTERS_COUNT
    )
    vip_dhcp_allocation: EnvVar = EnvVar(["VIP_DHCP_ALLOCATION"], loader=lambda x: bool(strtobool(x)))

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
    configmap: EnvVar = EnvVar(["CONFIGMAP"], default=consts.DEFAULT_CONFIGMAP)
    ai_base_version: EnvVar = EnvVar(["AI_BASE_VERSION"], default=consts.DEFAULT_AI_BASE_VERSION)
    deployment_service: EnvVar = EnvVar(["DEPLOYMENT_SERVICE"], default=consts.DEFAULT_DEPLOYMENT_SERVICE)
    spoke_namespace: str = EnvVar(["SPOKE_NAMESPACE"], default=consts.DEFAULT_SPOKE_NAMESPACE)
    olm_operators: EnvVar = EnvVar(
        ["OLM_OPERATORS"], loader=lambda operators: re.split(r"\s|,", operators.lower()), default=[]
    )
    custom_manifests: EnvVar = EnvVar(
        ["CUSTOM_MANIFESTS_FILES"],
        loader=lambda files: [m for path in re.split(r"\s|,", files) for m in Manifest.get_manifests(Path(path))],
        default=[],
    )
    platform: EnvVar = EnvVar(["PLATFORM"])
    tf_platform: EnvVar = EnvVar(["TF_PLATFORM", "PLATFORM"], default=env_defaults.DEFAULT_PLATFORM)
    user_managed_networking: EnvVar = EnvVar(
        ["USER_MANAGED_NETWORKING"],
        loader=lambda x: bool(strtobool(x)),
        default=env_defaults.DEFAULT_USER_MANAGED_NETWORKING,
    )
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
    cpu_architecture: EnvVar = EnvVar(["CPU_ARCHITECTURE"])
    day2_cpu_architecture: EnvVar = EnvVar(["DAY2_CPU_ARCHITECTURE"])

    single_node_ip: EnvVar = EnvVar(["SINGLE_NODE_IP"], default=env_defaults.DEFAULT_SINGLE_NODE_IP)
    worker_cpu_mode: EnvVar = EnvVar(["WORKER_CPU_MODE"], default=env_defaults.DEFAULT_TF_CPU_MODE)
    master_cpu_mode: EnvVar = EnvVar(["MASTER_CPU_MODE"], default=env_defaults.DEFAULT_TF_CPU_MODE)
    iso_download_path: EnvVar = EnvVar(["ISO_DOWNLOAD_PATH", "ISO"])  # todo replace ISO env var->ISO_DOWNLOAD_PATH
    hyperthreading: EnvVar = EnvVar(["HYPERTHREADING"])
    network_type: EnvVar = EnvVar(["NETWORK_TYPE"])
    disk_encryption_mode: EnvVar = EnvVar(["DISK_ENCRYPTION_MODE"], default=env_defaults.DEFAULT_DISK_ENCRYPTION_MODE)
    disk_encryption_roles: EnvVar = EnvVar(
        ["DISK_ENCRYPTION_ROLES"], default=env_defaults.DEFAULT_DISK_ENCRYPTION_ROLES
    )
    is_kube_api: EnvVar = EnvVar(
        ["ENABLE_KUBE_API"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_IS_KUBE_API
    )
    hold_installation: EnvVar = EnvVar(
        ["HOLD_INSTALLATION"], loader=lambda x: bool(strtobool(x)), default=env_defaults.DEFAULT_HOLD_INSTALLATION
    )
    reclaim_hosts: EnvVar = EnvVar(["RECLAIM_HOSTS"], loader=lambda x: bool(strtobool(x)), default=False)

    api_vip: EnvVar = EnvVar(["API_VIP"])
    ingress_vip: EnvVar = EnvVar(["INGRESS_VIP"])

    metallb_api_ip: EnvVar = EnvVar(["METALLB_API_IP"])
    metallb_ingress_ip: EnvVar = EnvVar(["METALLB_INGRESS_IP"])

    ipxe_boot: EnvVar = EnvVar(["IPXE_BOOT"], loader=lambda x: bool(strtobool(x)))

    vsphere_parent_folder: str = EnvVar(["VSPHERE_PARENT_FOLDER"], default=env_defaults.DEFAULT_VSHPERE_PARENT_FOLDER)
    vsphere_folder: str = EnvVar(["VSPHERE_FOLDER"])
    vsphere_cluster: EnvVar = EnvVar(["VSPHERE_CLUSTER"])
    vsphere_username: EnvVar = EnvVar(["VSPHERE_USERNAME"])
    vsphere_password: EnvVar = EnvVar(["VSPHERE_PASSWORD"])
    vsphere_network: EnvVar = EnvVar(["VSPHERE_NETWORK"])
    vsphere_server: EnvVar = EnvVar(["VSPHERE_VCENTER"])
    vsphere_datacenter: EnvVar = EnvVar(["VSPHERE_DATACENTER"])
    vsphere_datastore: EnvVar = EnvVar(["VSPHERE_DATASTORE"])

    nutanix_username: EnvVar = EnvVar(["NUTANIX_USERNAME"])
    nutanix_password: EnvVar = EnvVar(["NUTANIX_PASSWORD"])
    nutanix_endpoint: EnvVar = EnvVar(["NUTANIX_ENDPOINT"])
    nutanix_port: EnvVar = EnvVar(["NUTANIX_PORT"], loader=int)
    nutanix_cluster: EnvVar = EnvVar(["NUTANIX_CLUSTER_NAME"])
    nutanix_subnet: EnvVar = EnvVar(["NUTANIX_SUBNET_NAME"])

    # day2 libvirt target and VM network configuration
    day2_libvirt_uri: EnvVar = EnvVar(["DAY2_LIBVIRT_URI"])
    day2_machine_cidr: EnvVar = EnvVar(["DAY2_MACHINE_CIDR"])
    day2_provisioning_cidr: EnvVar = EnvVar(["DAY2_PROVISIONING_CIDR"])
    day2_machine_cidr6: EnvVar = EnvVar(["DAY2_MACHINE_CIDR6"])
    day2_provisioning_cidr6: EnvVar = EnvVar(["DAY2_PROVISIONING_CIDR6"])
    day2_network_if: EnvVar = EnvVar(["DAY2_NETWORK_IF"])
    day2_secondary_network_if: EnvVar = EnvVar(["DAY2_SECONDARY_NETWORK_IF"])

    oci_compartment_oicd: EnvVar = EnvVar(["OCI_COMPARTMENT"])
    oci_user_oicd: EnvVar = EnvVar(["OCI_USER"])
    oci_private_key_path: EnvVar = EnvVar(["OCI_PRIVATE_KEY_PATH"])
    oci_key_fingerprint: EnvVar = EnvVar(["OCI_PUBLIC_KEY_FINGERPRINT"])
    oci_tenancy_oicd: EnvVar = EnvVar(["OCI_TENANCY"])
    oci_region: EnvVar = EnvVar(["OCI_REGION"])
    oci_vcn_oicd: EnvVar = EnvVar(["OCI_VCN"])
    oci_public_subnet_oicd: EnvVar = EnvVar(["OCI_PUBLIC_SUBNET"])
    oci_private_subnet_oicd: EnvVar = EnvVar(["OCI_PRIVATE_SUBNET"])
    oci_extra_node_nsg_oicds: EnvVar = EnvVar(
        ["OCI_EXTRA_NODE_NSG_IDS"], default=[], loader=lambda oicd: re.split(r"\s|,", oicd)
    )
    oci_extra_lb_nsg_oicds: EnvVar = EnvVar(
        ["OCI_EXTRA_LOAD_BALANCER_NSG_IDS"], default=[], loader=lambda oicd: re.split(r"\s|,", oicd)
    )
    is_disconnected: EnvVar = EnvVar(["DISCONNECTED"], default="")
