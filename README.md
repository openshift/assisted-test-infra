# Test-Infra
This project deploys the OpenShift Assisted Installer in Minikube and spawns libvirt VMs that represent bare metal hosts.

# Prerequisites
- CentOS 8 or RHEL 8 host
- File system that supports d_type (see Troubleshooting section for more information)
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
There are different options to use test-infra, which can be found in the Makefile. Note that some make targets require `skipper`.

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
skipper make run_full_flow_with_install
```
Or to run it together with create_full_environment (requires sudo password):
````bash
make all
````
### Run full flow without install
To run the flow without the installation stage:
```bash
skipper make run_full_flow
```

### Run only deploy nodes (without pre deploy of all assisted service)
```bash
skipper make deploy_nodes or skipper make deploy_nodes_with_install
```

### Redeploy nodes
```bash
skipper make redeploy_nodes or skipper make redeploy_nodes_with_install
```

### Redeploy with assisted services
```bash
skipper make redeploy_all or skipper make redeploy_all_with_install
```

## Cleaning
Cleaning test-infra environment.

### Clean all include minikube
```bash
skipper make destroy
```

### Clean nodes only
```bash
skipper make destroy_nodes
```

### Delete all virsh resources
Sometimes you may need to delete all libvirt resources
```bash
skipper make delete_all_virsh_resources
```
