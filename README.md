**Table of contents**

- [⚠️ Warning ⚠️](docs/warning.md)
- [Overview](docs/overview.md)
- [Prerequisites](docs/prerequisites)
- [getting-started](docs/getting-started.md)
  - [Deployment parameters](#deployment-parameters)
    - [Components](#components)
    - [Deployment config](#deployment-config)
    - [Cluster configmap](#cluster-configmap)
  - [Installation parameters](#installation-parameters)
  - [Vsphere parameters](#vsphere-parameters)
  - [Instructions](#instructions)
    - [Host preparation](#host-preparation)
  - [Usage](#usage)
  - [Adding a new e2e flow](#adding-a-new-e2e-flow)
  - [Full flow cases](#full-flow-cases)
    - [Run full flow with install](#run-full-flow-with-install)
    - [Run full flow without install](#run-full-flow-without-install)
    - [Run base flow without configuring networking](#run-base-flow-without-configuring-networking)
    - [Run full flow with ipv6](#run-full-flow-with-ipv6)
    - [Redeploy nodes](#redeploy-nodes)
    - [Cleaning](#cleaning)
      - [Clean all include minikube](#clean-all-include-minikube)
      - [Clean nodes only](#clean-nodes-only)
      - [Delete all virsh resources](#delete-all-virsh-resources)
    - [Create cluster and download ISO](#create-cluster-and-download-iso)
    - [Deploy Assisted Service and Monitoring stack](#deploy-assisted-service-and-monitoring-stack)
    - [`deploy_assisted_service` and Create cluster and download ISO](#deploy_assisted_service-and-create-cluster-and-download-iso)
    - [start\_minikube and Deploy UI and open port forwarding on port 6008, allows to connect to it from browser](#start_minikube-and-deploy-ui-and-open-port-forwarding-on-port-6008-allows-to-connect-to-it-from-browser)
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
  - [Kind](#kind)
  - [On-prem](#on-prem)
  - [Run operator](#run-operator)
  - [Cluster-API-provider-agent](#cluster-api-provider-agent)
  - [Test iPXE boot flow](#test-ipxe-boot-flow)

## Prerequisites

- CentOS 8 / RHEL 8 / Rocky 8 / AlmaLinux 8 host
- File system that supports d_type
- Ideally on a bare metal host with at least 64G of RAM.
- Run as a user with password-less `sudo` access or be ready to enter `sudo` password for prepare phase.
- Make sure to unset the KUBECONFIG variable in the same shell where you run `make`.
- Get a valid pull secret (JSON string) from [redhat.com](https://console.redhat.com/openshift/install/pull-secret) if you want to test the installation (not needed for testing only the discovery flow). Export it as:

```bash
export PULL_SECRET='<pull secret JSON>'
# or alternatively, define PULL_SECRET_FILE="/path/to/pull/secret/file"
```

## Installation Guide

Check the [Installation Guide](GUIDE.md) for installation instructions.

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
| `USE_LOCAL_SERVICE`           | if equals `true`, assisted-service will be build from `assisted-test-infra/assisted-service` code |
| `DEBUG_SERVICE`               | if equals `true`, assisted-service will be build from `assisted-test-infra/assisted-service` code and deployed in debug mode, exposing port `40000` for `dlv` connection. |
| `LOAD_BALANCER_TYPE` | Set to `cluster-managed` if the load-balancer will be deployed by OpenShift, and `user-managed` if it will be deployed externally by the user. |

**Note** - When using `USE_LOCAL_SERVICE` or `DEBUG_SERVICE` local assisted-service code will be used. Therefore `bring_assisted_service.sh` script will not change the local service code unless it is missing. If you want to import assisted-service changes, you can use -
```bash
make bring_assisted_service SERVICE_REPO=<assisted-service repository to use> SERVICE_BASE_REF=<assisted-service branch to use>
```
before you run start the deployment.

### Deployment config

|     |     |
| --- | --- |
| `ASSISTED_SERVICE_HOST`              | FQDN or IP address to where assisted-service is deployed. Used when DEPLOY_TARGET="onprem". |
| `DEPLOY_MANIFEST_PATH`               | the location of a manifest file that defines image tags images to be used |
| `DEPLOY_MANIFEST_TAG`                | the Git tag of a manifest file that defines image tags to be used |
| `DEPLOY_TAG`                         | the tag to be used for all images (assisted-service, assisted-installer, agent, etc) this will override any other os parameters |
| `DEPLOY_TARGET`                      | Specifies where assisted-service will be deployed. Defaults to "minikube". Other options are "onprem" for installing as a podman pod and "kind". |
| `KUBECONFIG`                         | kubeconfig file path, default: <home>/.kube/config |
| `SERVICE_NAME`                       | assisted-service target service name, default: assisted-service |
| `OPENSHIFT_VERSION`                  | The OCP version which will be supported by the deployed components. Should be in `x.y` format |
| `OPENSHIFT_INSTALL_RELEASE_IMAGE`    | The OCP release image reference which will be supported by the deployed components. For example - `quay.io/openshift-release-dev/ocp-release:4.16.0-x86_64` |
| `INSTALL_WORKING_DIR`                | The path to a working directory where files like iPXE scripts, boot artefacts, etc are strored. For example `/tmp` |
| `MACHINE_CIDR_IPV4`                  | The machine cidr for e.g. remote libvirt. Default is `192.168.127.0/24` |
| `MACHINE_CIDR_IPV6`                  | The machine cidr for e.g. remote libvirt. Default is `1001:db9::/120` |
| `USE_DHCP_FOR_LIBVIRT`               | Use DHCP for libvirt on s390x architecture. If set to true, the `MAC_LIBVIRT_PREFIX` parameter must be specified. Default is `True`.  
| `MAC_LIBVIRT_PREFIX`                 | The mac used for DHCP for KVM. Example `54:52:00:00:7a:00`. The last two diggest will be increased for every node. The first node will get `54:52:00:00:7a:00` the second node will get `54:52:00:00:7a:01`

### Minikube configuration

|   |   |
|---|---|
| `MINIKUBE_DRIVER`| set minikube driver, default = kvm2 |
| `MINIKUBE_CPUS`| set amount of cpus, default = 4|
| `MINIKUBE_MEMORY`| set amount of memory, default = 8G|
| `MINIKUBE_DISK_SIZE`| set disk size, default = 50G |
| `MINIKUBE_HOME`| set default location for minikube, default = ~/.minikube |
| `MINIKUBE_REGISTRY_IMAGE`| set registry image, default = "quay.io/libpod/registry:2.8" |
### Cluster configmap

|     |     |
| --- | --- |
| `BASE_DNS_DOMAINS`                      | base DNS domains that are managed by assisted-service, format: domain_name:domain_id/provider_type. |
| `AUTH_TYPE`                             | configure the type of authentication assisted-service will use, default: none |
| `IPv4`                                  | Boolean value indicating if IPv4 is enabled. Default is yes |
| `IPv6`                                  | Boolean value indicating if IPv6 is enabled. Default is no |
| `STATIC_IPS`                            | Boolean value indicating if static networking should be enabled. Default is no |
| `IS_BONDED`                             | Boolean value indicating if bonding should be enabled. It also implies static networking. Default is no |
| `NUM_BONDED_SLAVES`                     | Integer value indicating the number of bonded slaves per bond. It is only used if bonding support is enabled. Default is 2 |
| `BONDING_MODE`                          | Bonding mode when bonding is in use. Default is active-backup |
| `OCM_BASE_URL`                          | OCM API URL used to communicate with OCM and AMS, default: https://api.integration.openshift.com/ |
| `OCM_CLIENT_ID`                         | ID of Service Account used to communicate with OCM and AMS for Agent Auth and Authz |
| `OCM_CLIENT_SECRET`                     | Password of Service Account used to communicate with OCM and AMS for Agent Auth and Authz |
| `JWKS_URL`                              | URL for retrieving the JSON Web Key Set (JWKS) used for verifying JWT tokens in authentication. Defaults to https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs |
| `OC_MODE`                               | if set, use oc instead of minikube |
| `OC_SCHEME`                             | Scheme for assisted-service url on oc, default: http |
| `OC_SERVER`                             | server for oc login, required if oc-token is provided, default: https://api.ocp.prod.psi.redhat.com:6443 |
| `OC_TOKEN`                              | token for oc login (an alternative for oc-user & oc-pass) |
| `OCM_SELF_TOKEN`                        | offline token token used to fetch JWT tokens for assisted-service authentication (from https://console.redhat.com/openshift/token)
| `ACKNOWLEDGE_DEPRECATED_OCM_SELF_TOKEN` | flag indicates acknowledgement of offline token deprecation when used. should be `yes` when `OCM_SELF_TOKEN` is used
| `PROXY`                                 | Set HTTP and HTTPS proxy with default proxy targets. The target is the default gateway in the network having the machine network CIDR |
| `SERVICE_BASE_URL`                      | update assisted-service config map SERVICE_BASE_URL parameter with given URL, including port and protocol |
| `PUBLIC_CONTAINER_REGISTRIES`           | comma-separated list of registries that do not require authentication for pulling assisted installer images |
| `ENABLE_KUBE_API`                       | If set, deploy assisted-service with Kube API controllers (minikube only) |
| `DISABLED_HOST_VALIDATIONS`             | comma-separated list of validation IDs to be excluded from the host validation process. |
| `SSO_URL`                               | URL used to fetch JWT tokens for assisted-service authentication |
| `CHECK_CLUSTER_VERSION`                 | If "True", the controller will wait for CVO to finish |
| `AGENT_TIMEOUT_START`                   | Update assisted-service config map AGENT_TIMEOUT_START parameter. Default is 3m.
| `OS_IMAGES`                             | A list of available OS images (one for each minor OCP version and CPU architecture) |
| `RELEASE_IMAGES`                        | A list of available release images (one for each minor OCP version and CPU architecture) |
| `NVIDIA_REQUIRE_GPU`                    | Boolean value indicating if NVIDIA GPU requirements should be enforced, default: `true` |
| `AMD_REQUIRE_GPU`                       | Boolean value indicating if AMD GPU requirements should be enforced, default: `true` |

## Installation parameters

|                              |                                                                                                                                                            |
|------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `BASE_DOMAIN`                | base domain, needed for DNS name, default: redhat.com                                                                                                      |
| `CLUSTER_ID`                 | cluster id, used for already existing cluster, e.g. after the deploy_nodes command                                                                         |
| `CLUSTER_NAME`               | cluster name, used as prefix for virsh resources, default: test-infra-cluster                                                                              |
| `HTTPS_PROXY_URL`            | A proxy URL to use for creating HTTPS connections outside the cluster                                                                                      |
| `HTTP_PROXY_URL`             | A proxy URL to use for creating HTTP connections outside the cluster                                                                                       |
| `ISO`                        | path to ISO to spawn VM with, if set vms will be spawn with this iso without creating cluster. File must have the '.iso' suffix                            |
| `MASTER_MEMORY`              | memory for master VM, default: 16384MB                                                                                                                     |
| `NETWORK_CIDR`               | network CIDR to use for virsh VM network, default: "192.168.126.0/24"                                                                                      |
| `NETWORK_NAME`               | virsh network name for VMs creation, default: test-infra-net                                                                                               |
| `NO_PROXY_VALUES`            | A comma-separated list of destination domain names, domains, IP addresses, or other network CIDRs to exclude proxying                                      |
| `NUM_MASTERS`                | number of VMs to spawn as masters, default: 3                                                                                                              |
| `NUM_WORKERS`                | number of VMs to spawn as workers, default: 0                                                                                                              |
| `OPENSHIFT_VERSION`          | OpenShift version to install, default taken from the deployed assisted-service (`/v2/openshift-versions`)                                                  |
| `HYPERTHREADING`             | Set node's CPU hyperthreading mode. Values are: all, none, masters, workers. default: all                                                                  |
| `DISK_ENCRYPTION_MODE`       | Set disk encryption mode. Right now assisted-test-infra only supports "tpmv2", which is also the default.                                                  |
| `DISK_ENCRYPTION_ROLES`      | Set node roles to apply disk encryption. Values are: all, none, masters, workers. default: none                                                            |
| `PULL_SECRET`                | pull secret to use for cluster installation command, no option to install cluster without it.                                                              |
| `PULL_SECRET_FILE`           | path and name to the file containing the pull secret to use for cluster installation command, no option to install cluster without it.                     |
| `REMOTE_SERVICE_URL`         | URL to remote assisted-service - run infra on existing deployment                                                                                          |
| `ROUTE53_SECRET`             | Amazon Route 53 secret to use for DNS domains registration.                                                                                                |
| `WORKER_MEMORY`              | memory for worker VM, default: 8892MB                                                                                                                      |
| `SSH_PUB_KEY`                | SSH public key to use for image generation, gives option to SSH to VMs, default: ~/.ssh/id_rsa.pub                                                         |
| `IPXE_BOOT`                  | Boots VMs using iPXE if set to `true`, default: `false`                                                                                                    |
| `PLATFORM`                   | The openshift platform to integrate with, one of: `baremetal`, `none`,`vsphere`, `external`, default: `baremetal`                                          |
| `KERNEL_ARGUMENTS`           | Update live ISO kernel arguments. JSON formatted string containing array of dictionaries each having 2 attributes: `operation` and `value`. Currently, only `append` operation is supported. |
| `CPU_ARCHITECTURE`           | CPU architecture of the nodes that will be part of the cluster, one of: `x86_64`, `arm64`, `s390x`, `ppc64le`, default: `x86_64`                           |
| `DAY2_CPU_ARCHITECTURE`      | CPU architecture of the nodes that will be part of the cluster in day2, one of: `x86_64`, `arm64`, `s390x`, `ppc64le` default:`x86_64`                     |
| `CUSTOM_MANIFESTS_FILES`     | List of local manifest files separated by commas or path to directory containing multiple manifests                                                        |
| `DISCONNECTED`               | Set to "true" if local mirror needs to be used                                                            |
| `REGISTRY_CA_PATH`           | Path to mirror registry CA bundle                                                            |
| `HOST_INSTALLER_ARGS`        | JSON formatted string used to customize installer arguments on all the hosts. Example: `{"args": ["--append-karg", "console=ttyS0"]}`                      |
| `LOAD_BALANCER_TYPE` | Set to `cluster-managed` if the load-balancer will be deployed by OpenShift, and `user-managed` if it will be deployed externally by the user. |
| `SET_INFRAENV_VERSION` | If `true`, sets the `osImageVersion` field on the `InfraEnv` to the `OPENSHIFT_VERSION` to ensure the discovery ISO uses this OCP version for tests, default: `false` |
| `OLM_OPERATORS` | Comma-separated list of OLM operators to install on the cluster (e.g., `mce,odf,metallb`) |
| `OLM_BUNDLES` | Comma-separated list of operator bundles to install on the cluster (e.g., `virtualization,openshift-ai`). Bundles are expanded to their constituent operators automatically | 

## Vsphere parameters

|     |     |
| --- | --- |
| `VSPHERE_CLUSTER`                 | vSphere cluster name, vsphere cluster is a cluster of hosts that it manages, mandatory for vsphere platform |
| `VSPHERE_VCENTER`                 | vSphere vcenter server ip address or fqdn (vCenter server name for vSphere API operations), mandatory for vsphere platform |
| `VSPHERE_DATACENTER`              | vSphere data center name, mandatory for vsphere platform |
| `VSPHERE_NETWORK`                 | vSphere publicly accessible network for cluster ingress and access. e.g VM Network, mandatory for vsphere platform |
| `VSPHERE_DATASTORE`               | vSphere data store name, mandatory for vsphere platform |
| `VSPHERE_USERNAME`                | vSphere vcenter server username, mandatory for vsphere platform |
| `VSPHERE_PASSWORD`                | vSphere vcenter server password, mandatory for vsphere platform |

## Redfish parameters

|     |     |
| --- | --- |
`REDFISH_ENABLED`                   | Redfish enable API for management hardware servers |
`REDFISH_USER`                      | Redfish remote management user |
`REDFISH_PASSWORD`                  | Redfish remote management password |
`REDFISH_MACHINES`                  | Redfish list of remote ipv4 managnments |

## External parameters

|     |     |
| --- | --- |
| `EXTERNAL_PLATFORM_NAME`            | Plaform name when using `external` platform                                                                                                         |
| `EXTERNAL_CLOUD_CONTROLLER_MANAGER` | Cloud controller manager when using `external` platform                                                                                             |

## Instructions

### Host preparation

On the bare metal host:

**Note**: don't do it from /root folder - it will break build image mounts and fail to run

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

## Adding a new e2e flow

Documentation about guidelines on how to create a new e2e test can be found [here](GUIDE.md#adding-a-new-e2e-flow)

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
make run deploy_nodes_with_networking
```

### Run base flow without configuring networking

Deploy the nodes without the network configuration and without the installation stage:

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
make image_build SERVICE_REPO=<assisted-service repository to use> SERVICE_BASE_REF=<assisted-service branch to use>
```

## Test with RHSSO Authentication

To test with Authentication, the following additional environment variables are required:

```
export AUTH_TYPE=rhsso
export OCM_BASE_URL=https://api.openshift.com
export JWKS_URL=https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/certs
```

There are currently two ways to authentication:
  1. Using service account - The service account need to have the necessary roles in order to make requests to OCM to check users roles/capabilities
  ```
  export OCM_CLIENT_ID=<SSO Service Account Name>
  export OCM_CLIENT_SECRET=<SSO Service Account Password>
  ```
  2. Using offline token (deprecated soon)
  ```
  export OCM_SELF_TOKEN=<User token from https://console.redhat.com/openshift/token>
  export ACKNOWLEDGE_DEPRECATED_OCM_SELF_TOKEN=yes
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

Set BIP_BUTANE_CONFIG env var to the path with butane config to be merged with bootstrap. Might be useful for promtail logging / other debug tasks

## Single Node - Bootstrap in place with Assisted Service and IPv6

To test single node bootstrap in place flow with assisted service and ipv6

```
export PULL_SECRET='<pull secret JSON>'
export OPENSHIFT_INSTALL_RELEASE_IMAGE=<relevant release image if needed>
export NUM_MASTERS=1
make deploy_nodes_with_install IPv6=yes IPv4=no
```

## Kind

Set ``DEPLOY_TARGET=kind`` to have a full construction of assisted-installer on top
of a kubernetes cluster which is running as one podman container:

```
# currently it's advisable to set it throughout the entire testing session because
# tests are also using this env-var to understand the networking layout
export DEPLOY_TARGET=kind

make run deploy_nodes_with_install
```

You can also create the kind cluster just by doing:
```
make create_hub_cluster DEPLOY_TARGET=kind
```

On ``kind`` mode you should be able to access the UI / API via ``http://<host>/``.

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

## Test iPXE boot flow
To test e2e deploying and installing nodes using iPXE, run the following:
```bash
export IPXE_BOOT=true
make setup
make run
make deploy_nodes_with_install
```

Optional environment variables that may be set for this test
|     |     |
| --- | --- |
| `IPXE_BOOT` | Boots VM hosts using iPXE if set to `true`, default: `false`|

**Notes**:
* A containerized Python server will be used to host the iPXE scripts for each cluster. This is due to the URL of the iPXE script file hosted in the assisted-service is longer than the character limit allowed in libvirt.

## Test MCE and storage

To test MCE deployed correctly with a storage driver, we should run the following:
```bash
export OLM_OPERATORS=mce,odf
export NUM_WORKERS=3
export WORKER_MEMORY=50000
export WORKER_CPU=20
export TEST_FUNC=test_mce_storage_post
make setup
make run
make deploy_nodes_with_install
export KUBECONFIG=./build/kubeconfig
export KUBECONFIG=$(find ${KUBECONFIG} -type f)
make test_parallel
```

export OLM_OPERATORS=mce,odf
