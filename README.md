# Test-Infra
This project deploys the OpenShift Assisted Installer in Minikube and spawns libvirt VMs that represent bare metal hosts.

# Prerequisites
- CentOS 8 or RHEL 8 host
- File system that supports d_type
- Ideally on a bare metal host with at least 64G of RAM.
- Run as a user with passwordless sudo access or be ready to enter sudo password for prepare phase.
- Get a valid pull secret (json string) from [redhat.com](https://cloud.redhat.com/openshift/install/pull-secret) if you want to test the installation (not needed for testing only the discovery flow). Export it as
```bash
export PULL_SECRET='<pull secret json>'
```

# Instructions


## Host preparation
Beaker node:
```bash
dnf install -y git make
cd /home/test # don't do it on /root it will breaks build image mounts and fail to run
git clone https://github.com/tsorya/test-infra.git
```
When using this infra for the first time on a host, run:
```bash
make create_full_environment
```
This will install required packages, configure libvirt, pull relevant docker images, and start Minikube.

## Usage
There are different options to use test-infra, which can be found in the Makefile.

## Full flow cases
The following is a list of stages that will be run:
1. Start Minikube if not started yet
1. Deploy services for assisted deployment on Minikube 
1. Create cluster in bm-inventory service
1. Download ISO image
1. Spawn required number of VMs from downloaded ISO with params that can be configured by os env (check makefile)
1. Wait until nodes are up and registered in bm-inventory
1. Set nodes roles in bm-inventory by matching VM names (worker/master)
1. Verify all nodes have required hardware to start installation
1. Install nodes
1. Download kubeconfig-noingress to build/kubeconfig
1. Waiting till nodes are in "installed" state, while verifying that they don't move to "error" state
1. Verifying cluster is in state "installed"
1. Download kubeconfig to build/kubeconfig


**Note**: Please make sure no previous cluster is running before running a new one (it will rewrite its build files).

### Run full flow with install
To run the full flow, including installation:
```bash
make run_full_flow_with_install
```
Or to run it together with create_full_environment (requires sudo password):
````bash
make all
````
### Run full flow without install
To run the flow without the installation stage:
```bash
make run_full_flow
```

### Run only deploy nodes (without pre deploy of all assisted service)
```bash
make deploy_nodes or make deploy_nodes_with_install
```

### Redeploy nodes
```bash
make redeploy_nodes or make redeploy_nodes_with_install
```

### Redeploy with assisted services
```bash
make redeploy_all or make redeploy_all_with_install
```

## Cleaning
Cleaning test-infra environment.

### Clean all include minikube
```bash
make destroy
```

### Clean nodes only
```bash
make destroy_nodes
```

### Delete all virsh resources
Sometimes you may need to delete all libvirt resources
```bash
make delete_all_virsh_resources
```

### Install cluster
Install cluster after nodes were deployed. Can take ClusterId as os env
```bash
make install_cluster 
```

### Create cluster and download iso
```bash
make download_iso
```

### deploy_bm_inventory and Create cluster and download iso
```bash
make download_iso_for_remote_use
```

### start_minikube and Deploy ui and and open port forwarding on port 6008, allows to connect to it from browser
```bash
make deploy_ui
```
### Kill all open port forwarding commands, will be part of destroy target
```bash
make kill_all_port_forwardings
```


## OS params used for configurations
~~~~
BMI_BRANCH          bm-inventory branch to use, default is master
IMAGE               path to iso to spawn vm with, if set vms will be spawn with this iso without creating cluster
NUM_MASTERS         number of vms to spawn as masters, default is 3 
WORKER_MEMORY       memory for worker vm, default 8892mb
MASTER_MEMORY       memory for master vm 16984
NUM_WORKERS         number of vms to spawn as workerm default 0
SSH_PUB_KEY         ssh public key to use for image generation, gives option to ssh to vms, default is in ssh_key/key_pub
PULL_SECRET         pull secret to use for cluster installation command, no option to install cluster without it.
CLUSTER_NAME        cluster name, used as prefix for virsh resources, default test-infra-cluster)
BASE_DOMAIN         base domain, needed for dns name, default redhat.com
NETWORK_CIDR        network cidr to use for virsh vm network, default "192.168.126.0/24"
CLUSTER_ID          cluster id , used for install_cluster command, default will be the last spawned cluster
NETWORK_NAME        virsh network name for vms creation, default test-infra-net
NETWORK_BRIDGE      network bridge to use while creating virsh network, default tt0
OPENSHIFT_VERSION   openshift version to install, default "4.4"
PROXY_URL:          proxy url that will be pass to live cd image
INVENTORY_URL:      update bm-inventory config map INVENTORY_URL param with given url
INVENTORY_PORT:     update bm-inventory config map INVENTORY_PORT with given port
AGENT_DOCKER_IMAGE: agent docker image to use, will update bm-inventory config map with given value
INSTALLER_IMAGE:    assisted-installer image to use, will update bm-inventory config map with given value
SERVICE:            bm-inventory image to use
DEPLOY_TAG:         the tag to be used for all images (bm-inventory, assisted-installer, agent, etc) this will override any other os params

~~~~

## Test bm-inventory image
```bash
make redeploy_all SERVICE=<image to test>
or 
export PULL_SECRET='<pull secret json>'; make redeploy_all_with_install SERVICE=<image to test>
```

## Test agent image
```bash
make redeploy_all AGENT_DOCKER_IMAGE=<image to test> 
or
make redeploy_all_with_install AGENT_DOCKER_IMAGE=<image to test>
```

## Test installer image
```bash
make redeploy_all INSTALLER_IMAGE=<image to test> 
or
export PULL_SECRET='<pull secret json>'; make redeploy_all_with_install INSTALLER_IMAGE=<image to test>
```

## Test installer, bm-inventory and agent images in the same flow
```bash
make redeploy_all INSTALLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test> SERVICE=<image to test>
or 
export PULL_SECRET='<pull secret json>'; make redeploy_all_with_install INSTALLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test>  SERVICE=<image to test>
```
# Test infra image

## Create and push new image will create new bm-inventory client, build new image and push image
```bash
make build_and_push_image IMAGE_NAME=<your full image path> IMAGE_TAG=<default is latest>
```
## Use new image, will pull image from hub, check that image is public, if tag is not latest update skipper yaml
```bash
make image_build IMAGE_NAME=<your image> IMAGE_TAG=<default is latest>
```
