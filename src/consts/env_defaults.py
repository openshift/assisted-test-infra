import os
from pathlib import Path

import consts

DEFAULT_NUMBER_OF_MASTERS: int = consts.NUMBER_OF_MASTERS
DEFAULT_DAY2_WORKERS_COUNT: int = 1
DEFAULT_DAY2_MASTERS_COUNT: int = 0
DEFAULT_WORKERS_COUNT: int = 2
DEFAULT_STORAGE_POOL_PATH: str = str(Path.cwd().joinpath("storage_pool"))
DEFAULT_SSH_PRIVATE_KEY_PATH: Path = Path.home() / ".ssh" / "id_rsa"
DEFAULT_SSH_PUBLIC_KEY_PATH: Path = Path.home() / ".ssh" / "id_rsa.pub"
DEFAULT_INSTALLER_KUBECONFIG = None
DEFAULT_LOG_FOLDER: Path = Path("/tmp/assisted_test_infra_logs")
DEFAULT_IMAGE_TYPE: str = consts.ImageType.MINIMAL_ISO
DEFAULT_TEST_TEARDOWN: bool = True
DEFAULT_PLATFORM: str = consts.Platforms.BARE_METAL
DEFAULT_USER_MANAGED_NETWORKING: bool = False
DEFAULT_CONTROL_PLANE_COUNT: int = consts.ControlPlaneCount.THREE
DEFAULT_DOWNLOAD_IMAGE: bool = True
DEFAULT_VERIFY_SSL: bool = True
DEFAULT_IS_IPV4: bool = True
DEFAULT_IS_IPV6: bool = False
DEFAULT_ADDITIONAL_NTP_SOURCE: str = consts.DEFAULT_ADDITIONAL_NTP_SOURCE
DEFAULT_STATIC_IPS: bool = False
DEFAULT_IS_BONDED: bool = False
DEFAULT_NUM_BONDED_SLAVES: int = 2
DEFAULT_BONDING_MODE: str = "active-backup"
DEFAULT_BOOTSTRAP_IN_PLACE: bool = False
DEFAULT_NETWORK_NAME: str = consts.TEST_NETWORK
DEFAULT_SINGLE_NODE_IP: str = ""
DEFAULT_TF_CPU_MODE: str = consts.HOST_PASSTHROUGH_CPU_MODE
DEFAULT_IMAGE_FOLDER: Path = Path(consts.IMAGE_FOLDER)
DEFAULT_IMAGE_FILENAME: str = "installer-image.iso"
DEFAULT_NETWORK_TYPE: str = consts.NetworkType.OpenShiftSDN
DEFAULT_DISK_ENCRYPTION_MODE: str = consts.DiskEncryptionMode.TPM_VERSION_2
DEFAULT_DISK_ENCRYPTION_ROLES: str = consts.DiskEncryptionRoles.NONE
DEFAULT_IS_KUBE_API: bool = False
DEFAULT_HOLD_INSTALLATION: bool = False
DEFAULT_MULTI_VERSION: bool = False
DEFAULT_BASE_DNS_DOMAIN = consts.REDHAT_DNS_DOMAIN
DEFAULT_VSHPERE_PARENT_FOLDER: str = "assisted-test-infra"
TF_APPLY_ATTEMPTS = int(os.getenv("TF_APPLY_ATTEMPTS", 1))
DEFAULT_EXTERNAL_PLATFORM_NAME = "test-infra"
DEFAULT_EXTERNAL_CLOUD_CONTROLLER_MANAGER = ""
DEFAULT_LOAD_BALANCER_TYPE: str = consts.LoadBalancerType.CLUSTER_MANAGED.value
DEFAULT_USE_DHCP_FOR_LIBVIRT: bool = False
