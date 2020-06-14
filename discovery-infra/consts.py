import os

TF_FOLDER = "build/terraform"
TFVARS_JSON_FILE = os.path.join(TF_FOLDER, "terraform.tfvars.json")
IMAGE_FOLDER = "/tmp/images"
IMAGE_PATH = "%s/installer-image.iso" % IMAGE_FOLDER
STORAGE_PATH = "/var/lib/libvirt/openshift-images"
SSH_KEY = "ssh_key/key.pub"
NODES_REGISTERED_TIMEOUT = 180
TF_TEMPLATE = "terraform_files"
STARTING_IP_ADDRESS = "192.168.126.10"
NUMBER_OF_MASTERS = 3
TEST_INFRA = "test-infra"
CLUSTER = "%s-cluster" % TEST_INFRA
CLUSTER_PREFIX = "%s-" % CLUSTER
TEST_NETWORK = "%s-net" % TEST_INFRA
DEFAULT_CLUSTER_KUBECONFIG_PATH = "build/kubeconfig"
WAIT_FOR_BM_API = 900


class NodeRoles:
    WORKER = "worker"
    MASTER = "master"


class NodesStatus:
    INSUFFICIENT = "insufficient"
    KNOWN = "known"
    INSTALLING = "installing"
    INSTALLED = "installed"
    ERROR = "error"


class ClusterStatus:
    INSTALLED = "installed"
    READY = "ready"
    INSTALLING = "installing"
