# Test-Infra

This project deploys the OpenShift Assisted Installer in Minikube and spawns libvirt VMs that represent bare metal hosts.

**Table of contents**

- [Test-Infra](#test-infra)
  - [Prerequisites](#prerequisites)
  - [Installation Guide](#installation-guide)
  - [OS parameters used for configuration](#os-parameters-used-for-configuration)
  - [Instructions](#instructions)
    - [Host preparation](#host-preparation)
  - [Usage](#usage)
  - [Full flow cases](#full-flow-cases)
    - [Run full flow with install](#run-full-flow-with-install)
    - [Run full flow without install](#run-full-flow-without-install)
    - [Run only deploy nodes (without pre deploy of all assisted service)](#run-only-deploy-nodes-without-pre-deploy-of-all-assisted-service)
    - [Redeploy nodes](#redeploy-nodes)
    - [Redeploy with assisted services](#redeploy-with-assisted-services)
    - [Cleaning](#cleaning)
      - [Clean all include minikube](#clean-all-include-minikube)
      - [Clean nodes only](#clean-nodes-only)
      - [Delete all virsh resources](#delete-all-virsh-resources)
    - [Install cluster](#install-cluster)
    - [Create cluster and download ISO](#create-cluster-and-download-iso)
    - [Deploy Assisted Service and Monitoring stack](#deploy-assisted-service-and-monitoring-stack)
    - [`deploy_assisted_service` and Create cluster and download ISO](#deploy_assisted_service-and-create-cluster-and-download-iso)
    - [start_minikube and Deploy UI and open port forwarding on port 6008, allows to connect to it from browser](#start_minikube-and-deploy-ui-and-open-port-forwarding-on-port-6008-allows-to-connect-to-it-from-browser)
    - [Kill all open port forwarding commands, will be part of destroy target](#kill-all-open-port-forwarding-commands-will-be-part-of-destroy-target)
  - [Test `assisted-service` image](#test-assisted-service-image)
    - [Test agent image](#test-agent-image)
    - [Test installer image or controller image](#test-installer-image-or-controller-image)
  - [Test installer, controller, `assisted-service` and agent images in the same flow](#test-installer-controller-assisted-service-and-agent-images-in-the-same-flow)
    - [Test infra image](#test-infra-image)
- [In case you would like to build the image with a different `assisted-service` client](#in-case-you-would-like-to-build-the-image-with-a-different-assisted-service-client)

## Prerequisites

- CentOS 8 or RHEL 8 host
- File system that supports d_type
- Ideally on a bare metal host with at least 64G of RAM.
- Run as a user with password-less `sudo` access or be ready to enter `sudo` password for prepare phase.
- Get a valid pull secret (JSON string) from [redhat.com](https://cloud.redhat.com/openshift/install/pull-secret) if you want to test the installation (not needed for testing only the discovery flow). Export it as

```bash
export PULL_SECRET='<pull secret JSON>'
```

## Installation Guide

Check the [Install Guide](GUIDE.md) for installation instructions.

## OS parameters used for configuration

| Variable                 | Description                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| SERVICE_BRANCH               | assisted-service branch to use, default: master                                                                                     |
| SERVICE_REPO               | assisted-service repository to use, default: https://github.com/openshift/assisted-service                                                                                     |
| ISO                      | path to ISO to spawn VM with, if set vms will be spawn with this iso without creating cluster. File must have the '.iso' suffix |
| NUM_MASTERS              | number of VMs to spawn as masters, default: 3                                                                                   |
| WORKER_MEMORY            | memory for worker VM, default: 8892MB                                                                                           |
| MASTER_MEMORY            | memory for master VM, default: 16984MB                                                                                          |
| NUM_WORKERS              | number of VMs to spawn as workers, default: 0                                                                                   |
| SSH_PUB_KEY              | SSH public key to use for image generation, gives option to SSH to VMs, default: ssh_key/key_pub                                |
| PULL_SECRET              | pull secret to use for cluster installation command, no option to install cluster without it.                                   |
| ROUTE53_SECRET           | Amazon Route 53 secret to use for DNS domains registration.                                                                     |
| CLUSTER_NAME             | cluster name, used as prefix for virsh resources, default: test-infra-cluster                                                   |
| BASE_DOMAIN              | base domain, needed for DNS name, default: redhat.com                                                                           |
| BASE_DNS_DOMAINS         | base DNS domains that are managed by assisted-service, format: domain_name:domain_id/provider_type.                             |
| NETWORK_CIDR             | network CIDR to use for virsh VM network, default: "192.168.126.0/24"                                                           |
| CLUSTER_ID               | cluster id , used for install_cluster command, default: the last spawned cluster                                                |
| NETWORK_NAME             | virsh network name for VMs creation, default: test-infra-net                                                                    |
| NETWORK_BRIDGE           | network bridge to use while creating virsh network, default: tt0                                                                |
| OPENSHIFT_VERSION        | OpenShift version to install, default: "4.5"                                                                                    |
| HTTP_PROXY_URL           | A proxy URL to use for creating HTTP connections outside the cluster |
| HTTPS_PROXY_URL          | A proxy URL to use for creating HTTPS connections outside the cluster |
| NO_PROXY                 | A comma-separated list of destination domain names, domains, IP addresses, or other network CIDRs to exclude proxying |
| SERVICE_BASE_URL         | update assisted-service config map SERVICE_BASE_URL parameter with given URL, including port and protocol                       |
| AGENT_DOCKER_IMAGE       | agent docker image to use, will update assisted-service config map with given value                                             |
| INSTALLER_IMAGE          | assisted-installer image to use, will update assisted-service config map with given value                                       |
| SERVICE                  | assisted-service image to use                                                                                                   |
| DEPLOY_TAG               | the tag to be used for all images (assisted-service, assisted-installer, agent, etc) this will override any other os parameters |
| IMAGE_BUILDER            | image-builder image to use, will update assisted-service config map with given value                                            |
| CONNECTIVITY_CHECK_IMAGE | connectivity-check image to use, will update assisted-service config map with given value                                       |
| HARDWARE_INFO_IMAGE      | hardware-info image to use, will update assisted-service config map with given value                                            |
| INVENTORY_IMAGE          | assisted-service image to be updated in assisted-service config map with given value                                            |
| OC_MODE                  | if set, use oc instead of minikube                                                                                              |
| OC_TOKEN                 | token for oc login (an alternative for oc-user & oc-pass)                                                                       |
| OC_SERVER                | server for oc login, required if oc-token is provided, default: https://api.ocp.prod.psi.redhat.com:6443                        |
| OC_SCHEME                | Scheme for assisted-service url on oc, default: http                                                                            |
| SERVICE_NAME             | assisted-service target service name, default: assisted-service                                                                 |
| KUBECONFIG               | kubeconfig file path, default: <home>/.kube/config                                                                              |
| ENABLE_AUTH              | configure assisted-service to authenticate API requests, default: false                                                         |
| OFFLINE_TOKEN            | token used to fetch JWT tokens for assisted-service authentication (from https://cloud.redhat.com/openshift/token)              |
| SSO_URL                  | URL used to fetch JWT tokens for assisted-service authentication                                                                |
| PROFILE                  | minikube profile for assisted-installer deployment, default: assisted-installer                                                 |

## Instructions

### Host preparation

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
1. Create cluster in `assisted-service` service
1. Download ISO image
1. Spawn required number of VMs from downloaded ISO with parameters that can be configured by OS environment (check makefile)
1. Wait until nodes are up and registered in `assisted-service`
1. Set nodes roles in `assisted-service` by matching VM names (worker/master)
1. Verify all nodes have required hardware to start installation
1. Install nodes
1. Download `kubeconfig-noingress` to build/kubeconfig
1. Waiting till nodes are in `installed` state, while verifying that they don't move to `error` state
1. Verifying cluster is in state `installed`
1. Download kubeconfig to build/kubeconfig

**Note**: Please make sure no previous cluster is running before running a new one (it will rewrite its build files).

### Run full flow with install

To run the full flow, including installation:

```bash
make run_full_flow_with_install
```

Or to run it together with create_full_environment (requires `sudo` password):

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

### Cleaning

Following sections show how to perform cleaning of test-infra environment.

#### Clean all include minikube

```bash
make destroy
```

#### Clean nodes only

```bash
make destroy_nodes
```

#### Delete all virsh resources

Sometimes you may need to delete all libvirt resources

```bash
make delete_all_virsh_resources
```

### Install cluster

Install cluster after nodes were deployed. Can take ClusterId as OS environment

```bash
make install_cluster
```

### Create cluster and download ISO

```bash
make download_iso
```

### Deploy Assisted Service and Monitoring stack

```bash
make run
make deploy_monitoring
```

### `deploy_assisted_service` and Create cluster and download ISO

```bash
make download_iso_for_remote_use
```

### start_minikube and Deploy UI and open port forwarding on port 6008, allows to connect to it from browser

```bash
make deploy_ui
```

### Kill all open port forwarding commands, will be part of destroy target

```bash
make kill_all_port_forwardings
```

## Test `assisted-service` image

```bash
make redeploy_all SERVICE=<image to test>
or
export PULL_SECRET='<pull secret JSON>'; make redeploy_all_with_install SERVICE=<image to test>
```

### Test agent image

```bash
make redeploy_all AGENT_DOCKER_IMAGE=<image to test>
or
make redeploy_all_with_install AGENT_DOCKER_IMAGE=<image to test>
```

### Test installer image or controller image

```bash
make redeploy_all INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test>
or
export PULL_SECRET='<pull secret JSON>'; make redeploy_all_with_install INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test>
```

## Test installer, controller, `assisted-service` and agent images in the same flow

```bash
make redeploy_all INSTALLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test> SERVICE=<image to test>
or
export PULL_SECRET='<pull secret JSON>'; make redeploy_all_with_install INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test> SERVICE=<image to test>
```

### Test infra image

Assisted-test-infra builds an image including all the prerequisites to handle this repository.

```bash
make image_build
```

# In case you would like to build the image with a different `assisted-service` client

```bash
make image_build SERVICE=<assisted service image URL>
```
