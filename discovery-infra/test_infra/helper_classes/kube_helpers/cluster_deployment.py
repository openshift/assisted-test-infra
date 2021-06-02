import logging
from pprint import pformat
from typing import List, Optional, Tuple, Union, Any

import waiting
from kubernetes.client import ApiClient, CustomObjectsApi
from test_infra import consts

from test_infra.consts.kube_api import (
    CRD_API_GROUP,
    DEFAULT_WAIT_FOR_AGENTS_TIMEOUT,
    DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT,
    HIVE_API_GROUP,
    HIVE_API_VERSION,
)
from .agent import Agent
from .base_resource import BaseCustomResource
from .common import ObjectReference
from .secret import Secret

logger = logging.getLogger(__name__)


class ClusterDeployment(BaseCustomResource):
    """
    A CRD that represents cluster in assisted-service.
    On creation the cluster will be registered to the service.
    On deletion it will be unregistered from the service.
    When has sufficient data installation will start automatically.
    """

    _plural = "clusterdeployments"
    _platform_field = {"platform": {"agentBareMetal": {"agentSelector": {}}}}

    def __init__(
        self,
        kube_api_client: ApiClient,
        name: str,
        namespace: str = consts.DEFAULT_NAMESPACE,
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace,
        )

        logger.info("created cluster deployment %s: %s", self.ref, pformat(yaml_data))

    def create(
        self,
        secret: Secret,
        base_domain: str = consts.DEFAULT_BASE_DNS_DOMAIN,
        agent_cluster_install_ref: Optional[ObjectReference] = None,
        **kwargs,
    ):
        body = {
            "apiVersion": f"{HIVE_API_GROUP}/{HIVE_API_VERSION}",
            "kind": "ClusterDeployment",
            "metadata": self.ref.as_dict(),
            "spec": {
                "clusterName": self.ref.name,
                "baseDomain": base_domain,
                "pullSecretRef": secret.ref.as_dict(),
            },
        }
        body["spec"].update(self._platform_field)

        if agent_cluster_install_ref:
            body["spec"]["clusterInstallRef"] = agent_cluster_install_ref.as_dict()

        body["spec"].update(kwargs)
        self.crd_api.create_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace,
        )

        logger.info("created cluster deployment %s: %s", self.ref, pformat(body))

    def patch(
        self,
        secret: Optional[Secret] = None,
        **kwargs,
    ) -> None:
        body = {"spec": kwargs}
        body["spec"]["platform"] = {"agentBareMetal": {}}

        spec = body["spec"]
        body["spec"].update(self._platform_field)

        if secret:
            spec["pullSecretRef"] = secret.ref.as_dict()

        if "agent_cluster_install_ref" in kwargs:
            spec["clusterInstallRef"] = kwargs["agent_cluster_install_ref"].as_dict()

        self.crd_api.patch_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        logger.info("patching cluster deployment %s: %s", self.ref, pformat(body))

    def annotate_install_config(self, install_config: str) -> None:
        body = {"metadata": {"annotations": {f"{CRD_API_GROUP}/install-config-overrides": install_config}}}

        self.crd_api.patch_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        logger.info("patching cluster install config %s: %s", self.ref, pformat(body))

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        logger.info("deleted cluster deployment %s", self.ref)

    def status(
        self,
        timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT,
    ) -> dict:
        """
        Status is a section in the CRD that is created after registration to
        assisted service and it defines the observed state of ClusterDeployment.
        Since the status key is created only after resource is processed by the
        controller in the service, it might take a few seconds before appears.
        """

        def _attempt_to_get_status() -> dict:
            return self.get()["status"]

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f"cluster {self.ref} status",
            expected_exceptions=KeyError,
        )

    def condition(
        self,
        cond_type,
        timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        for condition in self.status(timeout).get("conditions", []):
            if cond_type == condition.get("type"):
                return condition.get("status"), condition.get("reason"), condition.get("message")
        return None, None, None

    def wait_for_condition(
        self,
        cond_type: str,
        required_status: str,
        required_reason: Optional[str] = None,
        timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    ) -> None:
        def _has_required_condition() -> Optional[bool]:
            status, reason, message = self.condition(cond_type=cond_type, timeout=0.5)
            logger.info(
                f"waiting for condition <{cond_type}> to be in status <{required_status}>. "
                f"actual status is: {status} {reason} {message}"
            )
            if status == required_status:
                if required_reason:
                    return required_reason == reason
                return True
            return False

        logger.info(
            "Waiting till cluster will be in condition %s with status: %s " "reason: %s",
            cond_type,
            required_status,
            required_reason,
        )

        waiting.wait(
            _has_required_condition,
            timeout_seconds=timeout,
            waiting_for=f"cluster {self.ref} condition {cond_type} to be in {required_status}",
            sleep_seconds=10,
            expected_exceptions=waiting.exceptions.TimeoutExpired,
        )

    def list_agents(self) -> List[Agent]:
        return Agent.list(self.crd_api, self)

    def wait_for_agents(
        self,
        num_agents: int = 1,
        timeout: Union[int, float] = DEFAULT_WAIT_FOR_AGENTS_TIMEOUT,
    ) -> List[Agent]:
        def _wait_for_sufficient_agents_number() -> List[Agent]:
            agents = self.list_agents()
            return agents if len(agents) == num_agents else []

        return waiting.wait(
            _wait_for_sufficient_agents_number,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f"cluster {self.ref} to have {num_agents} agents",
        )
