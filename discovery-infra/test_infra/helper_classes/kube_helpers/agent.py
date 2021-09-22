from pprint import pformat
from typing import List, Union, Dict, Optional

import waiting

from typing import List, Union
from pprint import pformat

from kubernetes.client import ApiClient, CustomObjectsApi

from test_infra import consts
from ...consts.kube_api import CRD_API_GROUP, CRD_API_VERSION, DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT
from .base_resource import BaseCustomResource
from .common import ObjectReference, logger


class Agent(BaseCustomResource):
    """
    A CRD that represents host's agent in assisted-service.
    When host is registered to the cluster the service will create an Agent
    resource and assign it to the relevant cluster.
    In oder to start the installation, all assigned agents must be approved.
    """

    _plural = "agents"

    def __init__(
        self,
        kube_api_client: ApiClient,
        name: str,
        namespace: str = consts.DEFAULT_NAMESPACE,
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    @classmethod
    def list(
        cls,
        crd_api: CustomObjectsApi,
        cluster_deployment: "ClusterDeployment",
    ) -> List["Agent"]:
        resources = crd_api.list_namespaced_custom_object(
            group=CRD_API_GROUP,
            version=CRD_API_VERSION,
            plural=cls._plural,
            namespace=cluster_deployment.ref.namespace,
        )
        assigned_agents = []
        for item in resources.get("items", []):
            if item["spec"].get("clusterDeploymentName") is None:
                # Unbound late-binding agent, not part of the given cluster_deployment
                continue
            
            assigned_cluster_ref = ObjectReference(
                name=item["spec"]["clusterDeploymentName"]["name"],
                namespace=item["spec"]["clusterDeploymentName"]["namespace"],
            )
            if assigned_cluster_ref == cluster_deployment.ref:
                assigned_agents.append(
                    cls(
                        kube_api_client=cluster_deployment.crd_api.api_client,
                        name=item["metadata"]["name"],
                        namespace=item["metadata"]["namespace"],
                    )
                )

        return assigned_agents

    def create(self):
        raise RuntimeError("agent resource must be created by the assisted-installer operator")

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=CRD_API_GROUP,
            version=CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def patch(self, **kwargs) -> None:
        body = {"spec": kwargs}

        self.crd_api.patch_namespaced_custom_object(
            group=CRD_API_GROUP,
            version=CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        logger.info("patching agent %s: %s", self.ref, pformat(body))

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=CRD_API_GROUP,
            version=CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        logger.info("deleted agent %s", self.ref)

    def status(self, timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT) -> dict:
        def _attempt_to_get_status() -> dict:
            return self.get()["status"]

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f"agent {self.ref} status",
            expected_exceptions=KeyError,
        )

    @property
    def role(self) -> Optional[str]:
        return self.get()["spec"].get("role")

    def set_role(self, role: str) -> None:
        self.patch(role=role)
        logger.info(f"set agent {self.ref} role to {role}")

    def approve(self) -> None:
        self.patch(approved=True)
        logger.info("approved agent %s", self.ref)

    def bind(self, cluster_deployment: "ClusterDeployment") -> None:
        """
        Bind an unbound agent to a cluster deployment
        """
        self.patch(
            clusterDeploymentName={
                "name": cluster_deployment.ref.name,
                "namespace": cluster_deployment.ref.namespace,
            }
        )
        logger.info(f"Bound agent {self.ref} to cluster_deployment {cluster_deployment.ref}")

    @classmethod
    def wait_for_agents_to_be_ready_for_install(cls, agents: List["Agent"], nodes_number: int, timeout: Union[int, float] = consts.CLUSTER_INSTALLATION_TIMEOUT) -> None:
        for status_type in (
            consts.AgentStatus.SPEC_SYNCED,
            consts.AgentStatus.CONNECTED,
            consts.AgentStatus.REQUIREMENTS_MET,
            consts.AgentStatus.VALIDATED,
        ):
            cls.wait_till_all_agents_are_in_status(
                agents=agents,
                nodes_count=nodes_number,
                statusType=status_type,
                timeout=timeout,
            )

    @classmethod
    def wait_for_agents_to_install(cls, agents: List["Agent"], nodes_number: int, timeout: Union[int, float] = consts.CLUSTER_INSTALLATION_TIMEOUT) -> None:
        cls.wait_for_agents_to_be_ready_for_install(agents=agents, nodes_number=nodes_number, timeout=timeout)
        cls.wait_till_all_agents_are_in_status(
            agents=agents,
            statusType=consts.AgentStatus.INSTALLED,
            timeout=timeout,
        )

    @staticmethod
    def are_agents_in_status(
        agents: List["Agent"], statusType: str, status: str,
    ) -> bool:
        logger.info(
            "Asked agents to have the status [('%s', '%s')] and currently agent statuses are %s",
            statusType,
            status,
            [(condition["type"], condition["status"]) for agent in agents for condition in  agent.status()["conditions"]]
            )

        agents_in_status = [agent for agent in agents for condition in  agent.status()["conditions"] if condition["type"] == statusType and condition["status"] == status]
        if len(agents_in_status) >= len(agents):
            return True
        return False

    @staticmethod
    def wait_till_all_agents_are_in_status(
            agents: List["Agent"],
            statusType: str,
            timeout,
            interval=10,
    ) -> None:
        logger.info("Now Wait till agents have status as %s", statusType)

        waiting.wait(
            lambda: Agent.are_agents_in_status(
                agents,
                statusType,
                status="True",
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Agents to have %s status" % statusType,
        )
