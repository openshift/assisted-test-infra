# Test-Infra

This project deploys the OpenShift Assisted Installer in Minikube and spawns libvirt VMs that represent bare metal hosts.

# Prerequisites

- CentOS 8 or RHEL 8 host
- File system that supports d_type
- Ideally on a bare metal host with at least 64G of RAM.
- Run as a user with passwordless sudo access or be ready to enter sudo password for prepare phase.
- Get a valid pull secret (JSON string) from [redhat.com](https://cloud.redhat.com/openshift/install/pull-secret) if you want to test the installation (not needed for testing only the discovery flow). Export it as

```bash
export PULL_SECRET='<pull secret JSON>'
```

# Installation Guide

Check the [Install Guide](GUIDE.md) for installation instructions.

# Instructions

## Host preparation

On the bare metal host:

```bash
dnf install -y git make
cd /home/test # don't do it on /root it will breaks build image mounts and fail to run
git clone https://github.com/openshift/assisted-test-infra.git
```

When using this infra for the first time on a host, run:

```bash
make create_full_environment
```

This will install required packages, configure libvirt, pull relevant Docker images, and start Minikube.

## Usage

There are different options to use test-infra, which can be found in the makefile.

## Full flow cases

The following is a list of stages that will be run:

1. Start Minikube if not started yet
1. Deploy services for assisted deployment on Minikube
1. Create cluster in bm-inventory service
1. Download ISO image
1. Spawn required number of VMs from downloaded ISO with parameters that can be configured by OS env (check makefile)
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

```bash
make all
```

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

### Create cluster and download ISO

```bash
make download_iso
```

### Deploy BM Inventory and Monitoring stack

```bash
make run
make deploy_monitoring
```

### deploy_bm_inventory and Create cluster and download ISO

```bash
make download_iso_for_remote_use
```

### start_minikube and Deploy UI and and open port forwarding on port 6008, allows to connect to it from browser

```bash
make deploy_ui
```

### Kill all open port forwarding commands, will be part of destroy target

```bash
make kill_all_port_forwardings
```

## OS parameters used for configurations

```
BMI_BRANCH                bm-inventory branch to use, default: master
ISO                       path to ISO to spawn VM with, if set vms will be spawn with this iso without creating cluster. File must have the '.iso' suffix
NUM_MASTERS               number of VMs to spawn as masters, default: 3
WORKER_MEMORY             memory for worker VM, default: 8892MB
MASTER_MEMORY             memory for master VM, default: 16984MB
NUM_WORKERS               number of VMs to spawn as workers, default: 0
SSH_PUB_KEY               SSH public key to use for image generation, gives option to SSH to VMs, default: ssh_key/key_pub
PULL_SECRET               pull secret to use for cluster installation command, no option to install cluster without it.
ROUTE53_SECRET            Amazon Route 53 secret to use for DNS domains registration.
CLUSTER_NAME              cluster name, used as prefix for virsh resources, default: test-infra-cluster
BASE_DOMAIN               base domain, needed for DNS name, default: redhat.com
BASE_DNS_DOMAINS          base DNS domains that are managaed by bm-inventory, format: domain_name:domain_id/provider_type.
NETWORK_CIDR              network cidr to use for virsh VM network, default: "192.168.126.0/24"
CLUSTER_ID                cluster id , used for install_cluster command, default: the last spawned cluster
NETWORK_NAME              virsh network name for VMs creation, default: test-infra-net
NETWORK_MTU               virsh network MTU for VMs creation, default: 1500
NETWORK_BRIDGE            network bridge to use while creating virsh network, default: tt0
OPENSHIFT_VERSION         OpenShift version to install, default: "4.4"
PROXY_URL:                proxy URL that will be pass to live cd image
INVENTORY_URL:            update bm-inventory config map INVENTORY_URL param with given URL
INVENTORY_PORT:           update bm-inventory config map INVENTORY_PORT with given port
AGENT_DOCKER_IMAGE:       agent docker image to use, will update bm-inventory config map with given value
INSTALLER_IMAGE:          assisted-installer image to use, will update bm-inventory config map with given value
SERVICE:                  bm-inventory image to use
DEPLOY_TAG:               the tag to be used for all images (bm-inventory, assisted-installer, agent, etc) this will override any other os params
IMAGE_BUILDER:            image-builder image to use, will update bm-inventory config map with given value
CONNECTIVITY_CHECK_IMAGE  connectivity-check image to use, will update bm-inventory config map with given value
HARDWARE_INFO_IMAGE       hardware-info image to use, will update bm-inventory config map with given value
INVENTORY_IMAGE           bm-inventory image to be updated in bm-inventory config map with given value
```

## Test bm-inventory image

```bash
make redeploy_all SERVICE=<image to test>
or
export PULL_SECRET='<pull secret JSON>'; make redeploy_all_with_install SERVICE=<image to test>
```

## Test agent image

```bash
make redeploy_all AGENT_DOCKER_IMAGE=<image to test>
or
make redeploy_all_with_install AGENT_DOCKER_IMAGE=<image to test>
```

## Test installer image or controller image

```bash
make redeploy_all INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test>
or
export PULL_SECRET='<pull secret JSON>'; make redeploy_all_with_install INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test>
```

## Test installer, controller, bm-inventory and agent images in the same flow

```bash
make redeploy_all INSTALLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test> SERVICE=<image to test>
or
export PULL_SECRET='<pull secret JSON>'; make redeploy_all_with_install INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test> SERVICE=<image to test>
```

# Test infra image

Assisted-test-infra builds an image including all the prerequisites to handle this repository.

```bash
make image_build
```

# In case you would like to build the image with a different bm-inventory client

```bash
make image_build SERVICE=<bm inventory image URL>
```
