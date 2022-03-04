# Test-Infra

This project deploys the OpenShift Assisted Installer in Minikube and spawns libvirt VMs that represent bare metal hosts.

**Table of contents**

- [Test-Infra](#test-infra)
  - [Prerequisites](#prerequisites)
  - [Installation Guide](#installation-guide)
  - [Deployment parameters](#deployment-parameters)
    - [Components](#components)
    - [Deployment config](#deployment-config)
    - [Cluster configmap](#cluster-configmap)
  - [Installation parameters](#installation-parameters)
  - [Instructions](#instructions)
    - [Host preparation](#host-preparation)
  - [Usage](#usage)
  - [Full flow cases](#full-flow-cases)
    - [Run full flow with install](#run-full-flow-with-install)
    - [Run full flow without install](#run-full-flow-without-install)
    - [Run full flow with ipv6](#run-full-flow-with-ipv6)
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
  - [Test with RHSSO Authentication](#test-with-rhsso-authentication)
  - [Single Node - Bootstrap in place with Assisted Service](#single-node---bootstrap-in-place-with-assisted-service)
  - [Single Node - Bootstrap in place with Assisted Service and IPv6](#single-node---bootstrap-in-place-with-assisted-service-and-ipv6)
  - [On-prem](#on-prem)
  - [Run operator](#run-operator)
  - [Cluster-API-provider-agent](#Cluster-API-provider-agent)

## Prerequisites

- CentOS 8 or RHEL 8 host
- File system that supports d_type
- Ideally on a bare metal host with at least 64G of RAM.
- Run as a user with password-less `sudo` access or be ready to enter `sudo` password for prepare phase.
- Make sure to unset the KUBECONFIG variable in the same shell where you run `make`.
- Get a valid pull secret (JSON string) from [redhat.com](https://cloud.redhat.com/openshift/install/pull-secret) if you want to test the installation (not needed for testing only the discovery flow). Export it as:

```bash
export PULL_SECRET='<pull secret JSON>'
# or alternatively, define PULL_SECRET_FILE="/path/to/pull/secret/file"
```

## Installation Guide

Check the [Install Guide](GUIDE.md) for installation instructions.

## Deployment parameters

### Components

|     |     |
| --- | --- |
| `AGENT_DOCKER_IMAGE`          | agent docker image to use, will update assisted-service config map with given value |
| `INSTALLER_IMAGE`             | assisted-installer image to use, will update assisted-service config map with given value |
| `SERVICE`                     | assisted-service image to use |
| `SERVICE_BRANCH`              | assisted-service branch to use, default: master |
| `SERVICE_BASE_REF`            | assisted-service base reference to merge `SERVICE_BRANCH` with, default: master |
| `SERVICE_REPO`                | assisted-service repository to use, default: https://github.com/openshift/assisted-service |

### Deployment config

|     |     |
| --- | --- |
| `ASSISTED_SERVICE_HOST`       | FQDN or IP address to where assisted-service is deployed. Used when DEPLOY_TARGET="onprem". |
| `DEPLOY_MANIFEST_PATH`        | the location of a manifest file that defines image tags images to be used |
| `DEPLOY_MANIFEST_TAG`         | the Git tag of a manifest file that defines image tags to be used |
| `DEPLOY_TAG`                  | the tag to be used for all images (assisted-service, assisted-installer, agent, etc) this will override any other os parameters |
| `DEPLOY_TARGET`               | Specifies where assisted-service will be deployed. Defaults to "minikube". "onprem" will deploy assisted-service in a pod on the localhost. |
| `KUBECONFIG`                  | kubeconfig file path, default: <home>/.kube/config |
| `SERVICE_NAME`                | assisted-service target service name, default: assisted-service |

### Cluster configmap

|     |     |
| --- | --- |
| `BASE_DNS_DOMAINS`            | base DNS domains that are managed by assisted-service, format: domain_name:domain_id/provider_type. |
| `AUTH_TYPE`                   | configure the type of authentication assisted-service will use, default: none |
| `IPv4`                        | Boolean value indicating if IPv4 is enabled. Default is yes |
| `IPv6`                        | Boolean value indicating if IPv6 is enabled. Default is no |
| `STATIC_IPS`                  | Boolean value indicating if static networking should be enabled. Default is no |
| `OCM_BASE_URL`                | OCM API URL used to communicate with OCM and AMS, default: https://api.integration.openshift.com/ |
| `OCM_CLIENT_ID`               | ID of Service Account used to communicate with OCM and AMS for Agent Auth and Authz |
| `OCM_CLIENT_SECRET`           | Password of Service Account used to communicate with OCM and AMS for Agent Auth and Authz |
| `OC_MODE`                     | if set, use oc instead of minikube |
| `OC_SCHEME`                   | Scheme for assisted-service url on oc, default: http |
| `OC_SERVER`                   | server for oc login, required if oc-token is provided, default: https://api.ocp.prod.psi.redhat.com:6443 |
| `OC_TOKEN`                    | token for oc login (an alternative for oc-user & oc-pass) |
| `OFFLINE_TOKEN`               | token used to fetch JWT tokens for assisted-service authentication (from https://cloud.redhat.com/openshift/token)                          |
| `PROXY`                       | Set HTTP and HTTPS proxy with default proxy targets. The target is the default gateway in the network having the machine network CIDR |
| `SERVICE_BASE_URL`            | update assisted-service config map SERVICE_BASE_URL parameter with given URL, including port and protocol |
| `PUBLIC_CONTAINER_REGISTRIES` | comma-separated list of registries that do not require authentication for pulling assisted installer images |
| `ENABLE_KUBE_API`             | If set, deploy assisted-service with Kube API controllers (minikube only) |
| `DISABLED_HOST_VALIDATIONS`   | comma-separated list of validation IDs to be excluded from the host validation process. |
| `SSO_URL`                     | URL used to fetch JWT tokens for assisted-service authentication |
| `CHECK_CLUSTER_VERSION`       | If "True", the controller will wait for CVO to finish |
| `AGENT_TIMEOUT_START`         | Update assisted-service config map AGENT_TIMEOUT_START parameter. Default is 3m.
| `OS_IMAGES`                   | A list of available OS images (one for each minor OCP version and CPU architecture) |
| `RELEASE_IMAGES`              | A list of available release images (one for each minor OCP version and CPU architecture) |

## Installation parameters

|     |     |
| --- | --- |
| `BASE_DOMAIN`                 | base domain, needed for DNS name, default: redhat.com |
| `CLUSTER_ID`                  | cluster id, used for already existing cluster, e.g. after the deploy_nodes command |
| `CLUSTER_NAME`                | cluster name, used as prefix for virsh resources, default: test-infra-cluster |
| `HTTPS_PROXY_URL`             | A proxy URL to use for creating HTTPS connections outside the cluster |
| `HTTP_PROXY_URL`              | A proxy URL to use for creating HTTP connections outside the cluster |
| `ISO`                         | path to ISO to spawn VM with, if set vms will be spawn with this iso without creating cluster. File must have the '.iso' suffix |
| `MASTER_MEMORY`               | memory for master VM, default: 16984MB |
| `NETWORK_CIDR`                | network CIDR to use for virsh VM network, default: "192.168.126.0/24" |
| `NETWORK_NAME`                | virsh network name for VMs creation, default: test-infra-net |
| `NO_PROXY_VALUES`             | A comma-separated list of destination domain names, domains, IP addresses, or other network CIDRs to exclude proxying |
| `NUM_MASTERS`                 | number of VMs to spawn as masters, default: 3 |
| `NUM_WORKERS`                 | number of VMs to spawn as workers, default: 0 |
| `OPENSHIFT_VERSION`           | OpenShift version to install, default taken from the deployed assisted-service (`/v2/openshift-versions`) |
| `HYPERTHREADING`              | Set node's CPU hyperthreading mode. Values are: all, none, masters, workers. default: all |
| `DISK_ENCRYPTION_MODE`        | Set disk encryption mode. Right now assisted-test-infra only supports "tpmv2", which is also the default. |
| `DISK_ENCRYPTION_ROLES`       | Set node roles to apply disk encryption. Values are: all, none, masters, workers. default: none |
| `PULL_SECRET`                 | pull secret to use for cluster installation command, no option to install cluster without it. |
| `PULL_SECRET_FILE`            | path and name to the file containing the pull secret to use for cluster installation command, no option to install cluster without it. |
| `REMOTE_SERVICE_URL`          | URL to remote assisted-service - run infra on existing deployment |
| `ROUTE53_SECRET`              | Amazon Route 53 secret to use for DNS domains registration. |
| `WORKER_MEMORY`               | memory for worker VM, default: 8892MB |
| `SSH_PUB_KEY`                 | SSH public key to use for image generation, gives option to SSH to VMs, default: ~/.ssh/id_rsa.pub |

## Instructions

### Host preparation

On the bare metal host:

**Note**: don't do it from /root folder - it will breaks build image mounts and fail to run

```bash
dnf install -y git make
cd /home/test
git clone https://github.com/openshift/assisted-test-infra.git
```

When using this infra for the first time on a host, run:

```bash
make setup
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
make run deploy_nodes_with_install
```

Or to run it together with `setup` (requires `sudo` password):

```bash
make all
```

### Run full flow without install

To run the flow without the installation stage:

```bash
make run deploy_nodes
```

### Run full flow with ipv6

To run the flow with default IPv6 settings:

```bash
make deploy_nodes_with_install IPv4=no IPv6=yes
```

### Redeploy nodes

```bash
make redeploy_nodes
```

Or:

```bash
make redeploy_nodes_with_install
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
make destroy run SERVICE=<image to test>
```

### Test agent image

```bash
make destroy run AGENT_DOCKER_IMAGE=<image to test>
```

### Test installer image or controller image

```bash
make destroy run INSTALLER_IMAGE=<image to test> CONTROLLER_IMAGE=<image to test>
```

## Test installer, controller, `assisted-service` and agent images in the same flow

```bash
make destroy run INSTALLER_IMAGE=<image to test> AGENT_DOCKER_IMAGE=<image to test> SERVICE=<image to test>
```

### Test infra image

Assisted-test-infra builds an image including all the prerequisites to handle this repository.

```bash
make image_build
```

## In case you would like to build the image with a different `assisted-service` client

```bash
make image_build SERVICE=<assisted service image URL>
```

## Test with RHSSO Authentication

To test with Authentication, the following additional environment variables are required:

```
export AUTH_TYPE=rhsso
export OCM_CLIENT_ID=<SSO Service Account Name>
export OCM_CLIENT_SECRET=<SSO Service Account Password>
export OCM_BASE_URL=https://api.openshift.com
export OFFLINE_TOKEN=<User token from https://cloud.redhat.com/openshift/token>
```

- UI is not available when Authentication is enabled.
- The PULL_SECRET variable should be taken from the same Red Hat cloud environment as defined in OCM_URL (integration, stage or production).

## Single Node - Bootstrap in place with Assisted Service

To test single node bootstrap in place flow with assisted service

```
export PULL_SECRET='<pull secret JSON>'
export OPENSHIFT_INSTALL_RELEASE_IMAGE=<relevant release image if needed>
export NUM_MASTERS=1
make deploy_nodes_with_install
```

## Single Node - Bootstrap in place with Assisted Service and IPv6

To test single node bootstrap in place flow with assisted service and ipv6

```
export PULL_SECRET='<pull secret JSON>'
export OPENSHIFT_INSTALL_RELEASE_IMAGE=<relevant release image if needed>
export NUM_MASTERS=1
make deploy_nodes_with_install IPv6=yes IPv4=no
```

## On-prem

To test on-prem in the e2e flow, two additional environment variables need to be set:

```
export DEPLOY_TARGET=onprem
export ASSISTED_SERVICE_HOST=<fqdn-or-ip>
```

Setting DEPLOY_TARGET to "onprem" configures assisted-test-infra to deploy
the assisted-service using a pod on your local host.

ASSISTED_SERVICE_HOST defines where the assisted-service will be deployed. For "onprem" deployments, set it to the FQDN or IP address of the host.

Optionally, you can also provide OPENSHIFT_INSTALL_RELEASE_IMAGE and PUBLIC_CONTAINER_REGISTRIES:

```
export OPENSHIFT_INSTALL_RELEASE_IMAGE=quay.io/openshift-release-dev/ocp-release:4.7.0-x86_64
export PUBLIC_CONTAINER_REGISTRIES=quay.io
```

If you do not export the optional variables, it will run with the default specified in assisted-service/onprem-environment.

Then run the same commands described in the instructions above to execute the test.

To run the full flow:

```
make all
```

To cleanup after the full flow:

```
make destroy
```

## Run operator

The current implementation installs an OCP cluster using assisted service on minikube.
Afterwards, we install the assisted-service-operator on top of that cluster.
The first step would be removed once we could either:

- Have an OCP cluster easily (i.e. [CRC](https://developers.redhat.com/products/codeready-containers/overview))
- Install the assisted-service operator on top of pure-k8s cluster. (At the moment there are some OCP component prerequisites)

```bash
# Deploy AI
make run deploy_nodes_with_install

# Deploy AI Operator on top of the new cluster
export KUBECONFIG=./build/kubeconfig
make deploy_assisted_operator
```

Clear the operator deployment

```bash
make clear_operator
```

Run installation with the operator

```bash
export INSTALLER_KUBECONFIG=./build/kubeconfig
export TEST_FUNC=test_kube_api_ipv4
export TEST=./src/tests/test_kube_api.py
export TEST_TEARDOWN=false
make test
```

## Cluster-API-provider-agent
To test capi-provider e2e flow, few additional environment variables need to be set:
these environment variables result a bigger minikube instance required for this flow
```bash
# The following exports are required since the capi test flow requires more resources than the default minikube deployment provides
export MINIKUBE_HOME=/home
export MINIKUBE_DISK_SIZE=100g
export MINIKUBE_RAM_MB=12288
```
Setup minikube with assisted-installer (kube-api enabled):
```bash
export PULL_SECRET=<your pull secret>
ENABLE_KUBE_API=true make run
```

Deploy capi-provider-agent and hypershift:
```bash
make deploy_capi_env
```
Run the test:
```bash
ENABLE_KUBE_API=true make test TEST=./src/tests/test_kube_api.py TEST_FUNC=test_capi_provider KUBECONFIG=$HOME/.kube/config
```
