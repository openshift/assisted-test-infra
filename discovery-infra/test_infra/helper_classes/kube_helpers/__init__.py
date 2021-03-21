"""
kube_helpers package provides infra to deploy, manage and install cluster using
CRDs instead of restful API calls.

Simplest use of this infra is performed by calling cluster_deployment_context
fixture, must be called with a kube_api_client which is provided as a fixture
as well. With this context manager you will be able to manage a cluster
without need to handle registration and deregistration.

Example of usage:

with cluster_deployment_context(kube_api_client) as cluster_deployment:
    print(cluster_deployment.status())

An Agent CRD will be created for each registered host. In order to start the
installation all agents must be approved.
When a ClusterDeployment has sufficient data and the assigned agents are
approved, installation will be started automatically.
"""

from .cluster_deployment import \
    cluster_deployment_context, \
    deploy_default_cluster_deployment, \
    delete_cluster_deployment, \
    Platform,\
    InstallStrategy, \
    ClusterDeployment
from .secret import deploy_default_secret, Secret
from .agent import Agent
from .common import create_kube_api_client, ObjectReference

__all__ = (
    'cluster_deployment_context',
    'deploy_default_cluster_deployment',
    'delete_cluster_deployment',
    'deploy_default_secret',
    'create_kube_api_client',
    'Platform',
    'InstallStrategy',
    'ClusterDeployment',
    'Secret',
    'Agent',
    'ObjectReference'
)
