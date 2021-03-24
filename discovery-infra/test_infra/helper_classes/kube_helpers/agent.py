from typing import List
from pprint import pformat

from kubernetes.client import ApiClient, CustomObjectsApi

from tests.conftest import env_variables

from .common import logger, ObjectReference
from .base_resource import BaseCustomResource


class Agent(BaseCustomResource):
    """
    A CRD that represents host's agent in assisted-service.
    When host is registered to the cluster the service will create an Agent
    resource and assign it to the relevant cluster.
    In oder to start the installation, all assigned agents must be approved.
    """
    _api_group = 'adi.io.my.domain'
    _version = 'v1alpha1'
    _plural = 'agents'

    def __init__(
            self,
            kube_api_client: ApiClient,
            name: str,
            namespace: str = env_variables['namespace']
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    @classmethod
    def list(
            cls,
            crd_api: CustomObjectsApi,
            cluster_deployment: 'ClusterDeployment',
    ) -> List['Agent']:
        resources = crd_api.list_namespaced_custom_object(
            group=cls._api_group,
            version=cls._version,
            plural=cls._plural,
            namespace=cluster_deployment.ref.namespace,
        )
        assigned_agents = []
        for item in resources.get('items', []):
            assigned_cluster_ref = ObjectReference(
                name=item['spec']['clusterDeploymentName']['name'],
                namespace=item['spec']['clusterDeploymentName']['namespace']
            )
            if assigned_cluster_ref == cluster_deployment.ref:
                assigned_agents.append(
                    cls(
                        kube_api_client=cluster_deployment.crd_api.api_client,
                        name=item['metadata']['name'],
                        namespace=item['metadata']['namespace']
                    )
                )

        return assigned_agents

    def create(self):
        raise RuntimeError(
            'agent resource must be created by the assisted-installer operator'
        )

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=self._api_group,
            version=self._version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

    def patch(self, **kwargs) -> None:
        body = {'spec': kwargs}

        self.crd_api.patch_namespaced_custom_object(
            group=self._api_group,
            version=self._version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body
        )

        logger.info(
            'patching agent %s: %s', self.ref, pformat(body)
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=self._api_group,
            version=self._version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

        logger.info('deleted agent %s', self.ref)

    def status(self) -> dict:
        return self.get()['status']

    def approve(self) -> None:
        self.patch(approved=True)

        logger.info('approved agent %s', self.ref)
