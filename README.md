# Test-Infra

This project is test infrastructure project to support assisted openshift deployment.
The idea is to deploy all relevant services in minikube and to spawn libvirt vms that will be used as hosts.


# Pre-requisites
CentOS 8 or RHEL 8 host
file system that supports d_type (see Troubleshooting section for more information)
ideally on a bare metal host with at least 64G of RAM.

Run as a user with passwordless sudo access or be ready to enter sudo password for prepare phase.

Get a valid pull secret (json string) from https://cloud.redhat.com/openshift/install/pull-secret 
if you want to finish installation.(No need for without install flow) and export it as
```bash
    export PULL_SECRET='<pull secret json>'
```

# Instructions

## Host preparation
Need to install required packages, configure libvirt, pulling relevand docker image and starting minikube for the first time
```bash
    make create_full_environment
```

## Usage
There are different option to use test-infra. You can always look on Makefile and to see them.
The main problem with usage is that some make target requires "skipper" and some not

## Full flow cases
Full flow stages, please make sure no previous cluster is running(will rewrite its build files):
    
    1. Start minikube if not started yet
    2. Deploy services for assisted deployment on minikube 
    3. Creating cluster in bm-inventory service
    4. Downloading iso image
    5. Spawning required number of vms from downloaded iso with params that can be configured by os env(check makefile)
    6. Waiting till nodes are up and registered in bm-inventory
    7. Setting nodes roles in bm-inventory by matching vm names (worker/master)
    8. Verifying all nodes have required hardware to start installation

If required installation:
   
    9. Install nodes
    10.Download kubeconfig

### Run full flow with install
There is an option to run full flow
```bash
    skipper make run_full_flow_with_install
```
This option will require sudo password due to create_full_environment that will run on it too
````bash
    make all
````
### Run full flow without install
To run all the flow wihtout installation please run
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