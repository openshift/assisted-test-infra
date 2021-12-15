from pprint import pformat
from typing import List, Optional, Union

import waiting
from kubernetes.client import ApiClient, CustomObjectsApi

import consts

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
        cluster_deployment,
        agents_namespace=None,
    ) -> List["Agent"]:
        agents_namespace = agents_namespace or cluster_deployment.ref.namespace
        resources = crd_api.list_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=cls._plural,
            namespace=agents_namespace,
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
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def patch(self, **kwargs) -> None:
        body = {"spec": kwargs}

        self.crd_api.patch_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        logger.info("patching agent %s: %s", self.ref, pformat(body))

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        logger.info("deleted agent %s", self.ref)

    def status(self, timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT) -> dict:
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

    def bind(self, cluster_deployment) -> None:
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
    def wait_for_agents_to_be_ready_for_install(
        cls, agents: List["Agent"], timeout: Union[int, float] = consts.CLUSTER_READY_FOR_INSTALL_TIMEOUT
    ) -> None:
        for status_type in (
            consts.AgentStatus.SPEC_SYNCED,
            consts.AgentStatus.CONNECTED,
            consts.AgentStatus.REQUIREMENTS_MET,
            consts.AgentStatus.VALIDATED,
        ):
            cls.wait_till_all_agents_are_in_status(
                agents=agents,
                statusType=status_type,
                timeout=timeout,
            )

    @classmethod
    def wait_for_agents_to_install(
        cls, agents: List["Agent"], timeout: Union[int, float] = consts.CLUSTER_INSTALLATION_TIMEOUT
    ) -> None:
        cls.wait_for_agents_to_be_ready_for_install(agents=agents, timeout=timeout)
        cls.wait_till_all_agents_are_in_status(
            agents=agents,
            statusType=consts.AgentStatus.INSTALLED,
            timeout=timeout,
        )

    @staticmethod
    def are_agents_in_status(
        agents: List["Agent"],
        statusType: str,
        status: str,
    ) -> bool:
        agents_conditions = {
            agent.ref.name: {condition["type"]: condition["status"] for condition in agent.status()["conditions"]}
            for agent in agents
        }

        logger.info(
            f"Waiting for agents to have the condition '{statusType}' ="
            f" '{status}' and currently agent conditions are {agents_conditions}"
        )

        return all(agent_conditions.get(statusType, None) == status for agent_conditions in agents_conditions.values())

    @staticmethod
    def wait_till_all_agents_are_in_status(
        agents: List["Agent"],
        statusType: str,
        timeout,
        interval=10,
    ) -> None:
        logger.info(f"Now Wait till agents have status as {statusType}")

        waiting.wait(
            lambda: Agent.are_agents_in_status(
                agents,
                statusType,
                status="True",
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Agents to have {statusType} status",
        )
