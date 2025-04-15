# Getting Started

## Prerequisites

Before proceeding, ensure you meet all the requirements listed in the [Prerequisites](./prerequisites.md).

## Clone the Project

```bash
git clone https://github.com/openshift/assisted-test-infra.git
cd assisted-test-infra
```

## Setup

Ensure you have completed the [setup](./setup.md) at least once on your machine. You may need to run it again if the project's dependencies have changed since your last setup.

## Deploy Assisted Installer Components

This section guides you through deploying `assisted-service` and its related components.

Several deployment types and targets are supported. By default, the system deploys the components on a `kind` cluster running in a `podman`-based Kubernetes environment for end-to-end (e2e) testing, exposing the RESTful API.

To deploy, run:

```bash
make run
```

This command will deploy the following components:
1. `assisted-service`
1. `assisted-image-service`
1. `assisted-installer-ui`
1. `assisted-installer-config`
1. `PostgreSQL`
1. `MinIO`

The UI should now be accessible at:  
`http://$(hostname --ip):8060`

You can customize the deployment by setting environment variables for specific images:

```bash
export SERVICE=<service-image>
export IMAGE_SERVICE=<image-service-image>
export ASSISTED_UI=<ui-image>
export AGENT_DOCKER_IMAGE=<agent-image>
export INSTALLER_IMAGE=<installer-image>
export CONTROLLER_IMAGE=<controller-image>
export PSQL_IMAGE=<psql-image>
```

To target a specific OpenShift version and speed up the deployment:

```bash
export OPENSHIFT_VERSION=<x.y>  # e.g., 4.18
```

To learn more about deployment options and customization, refer to the [deployment guide](./assisted-deployment.md).

## Test Assisted Installer Components

Now that `assisted-service` and its components are deployed, you can test them.

Each deployment type offers different testing options. For the default deployment described above, you can use:

1. `make deploy_nodes` — Create a cluster and deploy hosts (networking not configured).
1. `make deploy_nodes_with_networking` — Create a cluster, deploy hosts, and configure networking.
1. `make deploy_nodes_with_install` — Full flow: create cluster, deploy hosts, configure networking, and start installation.

For more testing options and customization details, see the [testing guide](./assisted-testing.md).
