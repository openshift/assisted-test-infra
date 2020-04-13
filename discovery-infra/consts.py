import os

TF_FOLDER = "build/terraform"
TFVARS_JSON_FILE = os.path.join(TF_FOLDER, "terraform.tfvars.json")
IMAGE_PATH = "/tmp/installer-image.iso"
STORAGE_PATH = "/var/lib/libvirt/openshift-images"
SSH_KEY = "ssh_key/key.pub"
NODES_REGISTERED_TIMEOUT = 120
TF_TEMPLATE = "terraform_files"
STARTING_IP_ADDRESS = "192.168.126.10"
NUMBER_OF_MASTERS = 3
TEST_INFRA = "test-infra"
CLUSTER = "%s-cluster" % TEST_INFRA
CLUSTER_PREFIX = "%s-" % CLUSTER
TEST_NETWORK = "%s-net" % TEST_INFRA

WAIT_FOR_BM_API = 600


class NodeRoles:
    WORKER = "worker"
    MASTER = "master"
