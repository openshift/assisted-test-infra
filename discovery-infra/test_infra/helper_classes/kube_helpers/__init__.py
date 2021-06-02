"""
kube_helpers package provides infra to deploy, manage and install cluster using
CRDs instead of restful API calls.

Use this package as part of pytest infra with the fixture kube_api_context.
It provides a KubeAPIContext object which holds information about the resources
created as well as the kubernetes ApiClient.

Example of usage:

def test_kube_api_wait_for_install(kube_api_context):
    kube_api_client = kube_api_context.api_client
    cluster_deployment = deploy_default_cluster_deployment(
        kube_api_client, "test-cluster", **installation_params
    )
    cluster_deployment.wait_to_be_installing()

An Agent CRD will be created for each registered host. In order to start the
installation all agents must be approved.
When a ClusterDeployment has sufficient data and the assigned agents are
approved, installation will be started automatically.
"""

from .cluster_image_set import ClusterImageSet, ClusterImageSetReference
from .cluster_deployment import ClusterDeployment
from .agent import Agent
from .nmstate_config import NMStateConfig
from .secret import deploy_default_secret, Secret
from .infraenv import deploy_default_infraenv, InfraEnv, Proxy
from .agent_cluster_install import AgentClusterInstall
from .common import (
    create_kube_api_client,
    UnexpectedStateError,
    KubeAPIContext,
    ObjectReference,
)

__all__ = (
    "ClusterImageSet",
    "ClusterImageSetReference",
    "ClusterDeployment",
    "Secret",
    "Agent",
    "AgentClusterInstall",
    "KubeAPIContext",
    "ObjectReference",
    "InfraEnv",
    "NMStateConfig",
    "UnexpectedStateError",
    "deploy_default_secret",
    "deploy_default_infraenv",
    "create_kube_api_client",
)
