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
1. Download kubeconfig

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

### Wait for cluster to be installed
```bash
make wait_for_cluster
```

### Create cluster and download iso
```bash
make download_iso
```

### Deploy bm-inventory with external ip and open port forwarding on port 6000
```bash
make deploy_bm_inventory_with_external_ip
```

### Deploy bm-inventory with external ip and open port forwarding on port 6000
```bash
make deploy_bm_inventory_with_external_ip
```

### deploy_bm_inventory_with_external_ip and Create cluster and download iso
```bash
make download_iso_for_remote_use
```

### Deploy ui and and open port forwarding on port 6008, allows to connect to it from browser
```bash
mae deploy_ui
```

## OS params used for configurations
~~~~
BMI_BRANCH         bm-inventory branch to use, default is master
IMAGE              path to iso to spawn vm with, if set vms will be spawn with this iso without creating cluster
NUM_MASTERS        number of vms to spawn as masters, default is 3 
WORKER_MEMORY      memory for worker vm, default 8892mb
MASTER_MEMORY      memory for master vm 16984
NUM_WORKERS        number of vms to spawn as workerm default 0
SSH_PUB_KEY        ssh public key to use for image generation, gives option to ssh to vms, default is in ssh_key/key_pub
PULL_SECRET        pull secret to use for cluster installation command, no option to install cluster without it.
CLUSTER_NAME       cluster name, used as prefix for virsh resources, default test-infra-cluster)
BASE_DOMAIN        base domain, needed for dns name, default redhat
NETWORK_CIDR       network cidr to use for virsh vm network, default "192.168.126.0/24"
CLUSTER_ID         cluster id , used for install_cluster command, default will be the last spawned cluster
NETWORK_NAME       virsh network name for vms creation, default test-infra-net
NETWORK_BRIDGE     network bridge to use while creating virsh network, default tt0
OPENSHIFT_VERSION  openshift version to install, default "4.4"
PROXY_IP           proxy ip, used for download_iso target, proxy ip to pass on generating image
PROXY_PORT         proxy port, used for download_iso target, proxy port to pass on generating image
