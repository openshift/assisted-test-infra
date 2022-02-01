from enum import Enum
from typing import List

from .durations import MINUTE, HOUR

from assisted_service_client import models


class OpenshiftVersion(Enum):
    VERSION_4_6 = "4.6"
    VERSION_4_7 = "4.7"
    VERSION_4_8 = "4.8"
    VERSION_4_9 = "4.9"
    MULTI_VERSION = "all"


class NetworkType:
    OpenShiftSDN = "OpenShiftSDN"
    OVNKubernetes = "OVNKubernetes"


# Files & Directories
WORKING_DIR = "build"
TF_FOLDER = f"{WORKING_DIR}/terraform"
TFVARS_JSON_NAME = "terraform.tfvars.json"
TFSTATE_FILE = "terraform.tfstate"
IMAGE_FOLDER = "/tmp/test_images"
TF_MAIN_JSON_NAME = "main.tf"
BASE_IMAGE_FOLDER = "/tmp/images"
IMAGE_NAME = "installer-image.iso"
STORAGE_PATH = "/var/lib/libvirt/openshift-images"
DEFAULT_CLUSTER_KUBECONFIG_DIR_PATH = "build/kubeconfig"
RELEASE_IMAGES_PATH = "assisted-service/data/default_release_images.json"

TF_TEMPLATES_ROOT = "terraform_files"
TF_TEMPLATE_BARE_METAL_FLOW = f"{TF_TEMPLATES_ROOT}/baremetal"
TF_TEMPLATE_NONE_PLATFORM_FLOW = f"{TF_TEMPLATES_ROOT}/none"
TF_TEMPLATE_BARE_METAL_INFRA_ENV_FLOW = f"{TF_TEMPLATES_ROOT}/baremetal_infra_env"
TF_NETWORK_POOL_PATH = "/tmp/tf_network_pool.json"

# Timeouts
NODES_REGISTERED_TIMEOUT = 20 * MINUTE
DEFAULT_CHECK_STATUSES_INTERVAL = 5
CLUSTER_READY_FOR_INSTALL_TIMEOUT = 10 * MINUTE
CLUSTER_INSTALLATION_TIMEOUT = HOUR
CLUSTER_INSTALLATION_TIMEOUT_OCS = 95 * MINUTE
START_CLUSTER_INSTALLATION_TIMEOUT = 6 * MINUTE
INSTALLING_IN_PROGRESS_TIMEOUT = 15 * MINUTE
VALIDATION_TIMEOUT = 6 * MINUTE
NTP_VALIDATION_TIMEOUT = 10 * MINUTE
OCS_VALIDATION_TIMEOUT = 10 * MINUTE
CNV_VALIDATION_TIMEOUT = 10 * MINUTE
READY_TIMEOUT = 15 * MINUTE
DISCONNECTED_TIMEOUT = 10 * MINUTE
PENDING_USER_ACTION_TIMEOUT = 30 * MINUTE
ERROR_TIMEOUT = 10 * MINUTE
WAIT_FOR_BM_API = 15 * MINUTE

# Networking
DEFAULT_CLUSTER_NETWORKS_IPV4: List[models.ClusterNetwork] = [models.ClusterNetwork(cidr="172.30.0.0/16", host_prefix=23)]
DEFAULT_SERVICE_NETWORKS_IPV4: List[models.ServiceNetwork] = [models.ServiceNetwork(cidr="10.128.0.0/14")]
DEFAULT_MACHINE_NETWORKS_IPV4: List[models.MachineNetwork] = \
    [models.MachineNetwork(cidr="192.168.127.0/24"), models.MachineNetwork(cidr="192.168.145.0/24")]

DEFAULT_CLUSTER_NETWORKS_IPV6: List[models.ClusterNetwork] = [models.ClusterNetwork(cidr="2002:db8::/53", host_prefix=64)]
DEFAULT_SERVICE_NETWORKS_IPV6: List[models.ServiceNetwork] = [models.ServiceNetwork(cidr="2003:db8::/112")]
DEFAULT_MACHINE_NETWORKS_IPV6: List[models.MachineNetwork] = \
    [models.MachineNetwork(cidr="1001:db9::/120"), models.MachineNetwork(cidr="3001:db9::/120")]

DEFAULT_CLUSTER_NETWORKS_IPV4V6 = DEFAULT_CLUSTER_NETWORKS_IPV4 + DEFAULT_CLUSTER_NETWORKS_IPV6
DEFAULT_SERVICE_NETWORKS_IPV4V6 = DEFAULT_SERVICE_NETWORKS_IPV4 + DEFAULT_SERVICE_NETWORKS_IPV6
DEFAULT_MACHINE_NETWORKS_IPV4V6 = [DEFAULT_MACHINE_NETWORKS_IPV4[0], DEFAULT_MACHINE_NETWORKS_IPV6[0]]

DEFAULT_PROXY_SERVER_PORT = 3129
DEFAULT_LOAD_BALANCER_PORT = 6443

TEST_INFRA = "test-infra"
CLUSTER = CLUSTER_PREFIX = "%s-cluster" % TEST_INFRA
INFRA_ENV_PREFIX = "%s-infra-env" % TEST_INFRA
TEST_NETWORK = "test-infra-net-"
TEST_SECONDARY_NETWORK = "test-infra-secondary-network-"

HOST_PASSTHROUGH_CPU_MODE = "host-passthrough"
MASTER_TF_CPU_MODE = HOST_PASSTHROUGH_CPU_MODE
WORKER_TF_CPU_MODE = HOST_PASSTHROUGH_CPU_MODE
NUMBER_OF_MASTERS = 3
NAMESPACE_POOL_SIZE = 15
PODMAN_FLAGS = "--cgroup-manager=cgroupfs --storage-driver=vfs --events-backend=file"
DEFAULT_ADDITIONAL_NTP_SOURCE = "clock.redhat.com"
DEFAULT_BASE_DNS_DOMAIN = "redhat.com"
DEFAULT_NAMESPACE = 'assisted-installer'
DEFAULT_SPOKE_NAMESPACE = 'assisted-spoke-cluster'
DEFAULT_TEST_INFRA_DOMAIN = f".{CLUSTER_PREFIX}-{DEFAULT_NAMESPACE}.{DEFAULT_BASE_DNS_DOMAIN}"
TEST_TARGET_INTERFACE = "vnet3"
SUFFIX_LENGTH = 8

IP_NETWORK_ASSET_FIELDS = (
    "machine_cidr",
    "machine_cidr6",
    "provisioning_cidr",
    "provisioning_cidr6",
)
REQUIRED_ASSET_FIELDS = (
    "libvirt_network_if",
    "libvirt_secondary_network_if",
    *IP_NETWORK_ASSET_FIELDS,
)

class ImageType:
    FULL_ISO = "full-iso"
    MINIMAL_ISO = "minimal-iso"


class NodeRoles:
    WORKER = "worker"
    MASTER = "master"
    AUTO_ASSIGN = "auto-assign"


class NodesStatus:
    INSUFFICIENT = "insufficient"
    KNOWN = "known"
    INSTALLING = "installing"
    INSTALLING_IN_PROGRESS = "installing-in-progress"
    INSTALLING_PENDING_USER_ACTION = "installing-pending-user-action"
    INSTALLED = "installed"
    ERROR = "error"
    PENDING_FOR_INPUT = "pending-for-input"
    DAY2_INSTALLED = "added-to-existing-cluster"
    RESETING_PENDING_USER_ACTION = "resetting-pending-user-action"
    DISCONNECTED = "disconnected"
    INSUFFICIENT_UNBOUND = "insufficient-unbound"
    KNOWN_UNBOUND = "known-unbound"


class ClusterStatus:
    INSUFFICIENT = "insufficient"
    INSTALLED = "installed"
    READY = "ready"
    PREPARING_FOR_INSTALLATION = "preparing-for-installation"
    INSTALLING = "installing"
    FINALIZING = "finalizing"
    ERROR = "error"
    PENDING_FOR_INPUT = "pending-for-input"
    CANCELLED = "cancelled"
    INSTALLING_PENDING_USER_ACTION = "installing-pending-user-action"


class HostsProgressStages:
    START_INSTALLATION = "Starting installation"
    INSTALLING = "Installing"
    WRITE_IMAGE_TO_DISK = "Writing image to disk"
    WAIT_FOR_CONTROL_PLANE = "Waiting for control plane"
    REBOOTING = "Rebooting"
    WAIT_FOR_IGNITION = "Waiting for ignition"
    JOINED = "Joined"
    CONFIGURING = "Configuring"
    DONE = "Done"


class AgentStatus:
    SPEC_SYNCED = "SpecSynced"
    CONNECTED = "Connected"
    VALIDATED = "Validated"
    INSTALLED = "Installed"
    REQUIREMENTS_MET = "RequirementsMet"


all_host_stages = [HostsProgressStages.START_INSTALLATION, HostsProgressStages.INSTALLING,
                   HostsProgressStages.WRITE_IMAGE_TO_DISK, HostsProgressStages.WAIT_FOR_CONTROL_PLANE,
                   HostsProgressStages.REBOOTING, HostsProgressStages.WAIT_FOR_IGNITION,
                   HostsProgressStages.CONFIGURING, HostsProgressStages.JOINED, HostsProgressStages.DONE]


class Events:
    REGISTERED_CLUSTER = "Registered cluster"
    SUCCESSFULLY_REGISTERED_CLUSTER = "Successfully registered cluster"
    PENDING_FOR_INPUT = "to pending-for-input"
    GENERATED_IMAGE = "Generated image (SSH public key is set)"
    GENERATED_IMAGE_FULL = "Generated image (Image type is \"full-iso\", SSH public key is set)"
    GENERATED_IMAGE_MINIMAL = "Generated image (Image type is \"minimal-iso\", SSH public key is set)"
    DOWNLOAD_IMAGE = "Started image download"
    STARTED_DOWNLOAD_IMAGE = "Started image download (image type is \"full-iso\")"
    HOST_REGISTERED_TO_CLUSTER = ": registered to cluster"
    INSUFFICIENT = "insufficient"
    KNOWN = "to \"known\""
    READY = "to ready"
    CLUSTER_VALIDATION = "Cluster validation \'all-hosts-are-ready-to-install\' is now fixed"
    PREPARING_FOR_INSTALLATION = "updated status from \"known\" to \"preparing-for-installation\""
    PREPARING_SUCCESSFUL = "updated status from \"preparing-for-installation\" to \"preparing-successful\""
    SET_BOOTSTRAP = "set as bootstrap"
    INSTALLING = "updated status from \"preparing-successful\" to \"installing\""
    CLUSTER_PREPARED = "Cluster was prepared successfully for installation"
    CLUSTER_INSTALLING = "to installing"
    INSTALLING_IN_PROGRESS = "updated status from \"installing\" to \"installing-in-progress\""
    INSTALLATION_STAGE = "reached installation stage Starting installation"
    INSTALLING_PENDING_USER_ACTION = "installing-pending-user-action"
    WRITING_IMAGE_TO_DISK = "reached installation stage Writing image to disk"
    REBOOTING = "reached installation stage Rebooting"
    CONTROL_PLANE = "reached installation stage Waiting for control plane"
    IGNITION = "reached installation stage Waiting for ignition"
    CONFIGURING = "reached installation stage Configuring"
    JOINED = "reached installation stage Joined"
    DONE = "reached installation stage Done"
    CANCELLED_CLUSTER_INSTALLATION = "Cancelled cluster installation"
    CANCELLED_FOR_HOST = "Installation cancelled for host"
    CLUSTER_VERSION_DONE = "Operator cvo status: available message: Done"
    CANCELLED_STATUS = "to \"cancelled\""
    RESET_CLUSTER_INSTALLATION = "Reset cluster installation"
    RESET_FOR_HOST = "Installation reset for host"
    RESETTING_PENDING_USER_ACTION = "updated status from \"cancelled\" to \"resetting-pending-user-action\""
    INSTALLED = "updated status from \"installing-in-progress\" to \"installed\""
    FINALIZING = "to finalizing"
    SUCCESSFULLY_INSTALLED = "Successfully finished installing cluster"
    ERROR = "error"
    DAY2_INSTALLED = "added-to-existing-cluster"
    PROXY_SETTINGS_CHANGED = "Proxy settings changed"


class HostStatusInfo:
    WRONG_BOOT_ORDER = "Expected the host to boot from disk, but it booted the installation image"
    REBOOT_TIMEOUT = "Host failed to reboot within timeout"


class Platforms:
    BARE_METAL = 'baremetal'
    NONE = 'none'
    VSPHERE = 'vsphere'


class HighAvailabilityMode:
    FULL = 'Full'
    NONE = 'None'


class BaseAsset:
    MACHINE_CIDR = DEFAULT_MACHINE_NETWORKS_IPV4[0].cidr
    MACHINE_CIDR6 = DEFAULT_MACHINE_NETWORKS_IPV6[0].cidr
    PROVISIONING_CIDR = DEFAULT_MACHINE_NETWORKS_IPV4[1].cidr
    PROVISIONING_CIDR6 = DEFAULT_MACHINE_NETWORKS_IPV6[1].cidr
    NETWORK_IF = "tt1"
    SECONDARY_NETWORK_IF = "stt1"
