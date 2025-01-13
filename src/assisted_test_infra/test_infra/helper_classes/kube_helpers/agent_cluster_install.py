import os
from base64 import b64decode
from pprint import pformat
from typing import Any, Dict, List, Optional, Tuple, Union

import waiting
from kubernetes.client import ApiClient, CustomObjectsApi

import consts
from service_client import log

from .base_resource import BaseCustomResource, ObjectReference
from .cluster_image_set import ClusterImageSetReference
from .secret import Secret


class AgentClusterInstall(BaseCustomResource):
    """This CRD represents a request to provision an agent based cluster.
    In the AgentClusterInstall, the user can specify requirements like
    networking, number of control plane and workers nodes and more.
    The installation will start automatically if the required number of
    hosts is available, the hosts are ready to be installed and the Agents
    are approved.
    The AgentClusterInstall reflects the ClusterDeployment/Installation
    status through Conditions."""

    _api_group = "extensions.hive.openshift.io"
    _api_version = "v1beta1"
    _plural = "agentclusterinstalls"
    _kind = "AgentClusterInstall"
    _requirements_met_condition_name = "RequirementsMet"
    _completed_condition_name = "Completed"

    def __init__(
        self,
        kube_api_client: ApiClient,
        name: str,
        namespace: str = consts.DEFAULT_NAMESPACE,
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)
        self.ref.kind = self._kind
        self.ref.group = self._api_group
        self.ref.version = self._api_version

    def create(
        self,
        cluster_deployment_ref: ObjectReference,
        cluster_cidr: str,
        host_prefix: int,
        service_network: str,
        control_plane_agents: int,
        **kwargs,
    ) -> None:
        body = {
            "apiVersion": f"{self._api_group}/{self._api_version}",
            "kind": self._kind,
            "metadata": self.ref.as_dict(),
            "spec": self._get_spec_dict(
                cluster_deployment_ref=cluster_deployment_ref,
                cluster_cidr=cluster_cidr,
                host_prefix=host_prefix,
                service_network=service_network,
                control_plane_agents=control_plane_agents,
                **kwargs,
            ),
        }

        self.crd_api.create_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace,
        )

        log.info("created agentclusterinstall %s: %s", self.ref, pformat(body))

    def patch(self, **kwargs) -> None:
        body = {"spec": kwargs}

        self.crd_api.patch_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        log.info("patching agentclusterinstall %s: %s", self.ref, pformat(body))

    def set_machine_networks(self, machine_cidrs):
        machine_networks: list[dict[str, str]] = []
        for machine_cidr in machine_cidrs:
            machine_networks.append({"cidr": machine_cidr})

        self.patch(networking={"machineNetwork": machine_networks})

    def set_api_vip(self, vip):
        self.patch(apiVIPs=[vip])

    def set_ingress_vip(self, vip):
        self.patch(ingressVIPs=[vip])

    def _get_spec_dict(
        self,
        cluster_deployment_ref: ObjectReference,
        cluster_cidr: str,
        host_prefix: int,
        service_network: str,
        control_plane_agents: int,
        **kwargs,
    ) -> dict:
        spec = {
            "clusterDeploymentRef": cluster_deployment_ref.as_dict(),
            "imageSetRef": kwargs.pop("image_set_ref", ClusterImageSetReference()).as_dict(),
            "networking": {
                "clusterNetwork": [
                    {
                        "cidr": cluster_cidr,
                        "hostPrefix": host_prefix,
                    }
                ],
                "serviceNetwork": [service_network],
            },
            "provisionRequirements": {
                "controlPlaneAgents": control_plane_agents,
                "workerAgents": kwargs.pop("worker_agents", 0),
            },
        }

        if "api_vips" in kwargs:
            spec["apiVIPs"] = kwargs.pop("api_vips")

        if "ingress_vips" in kwargs:
            spec["ingressVIPs"] = kwargs.pop("ingress_vips")

        if "ssh_pub_key" in kwargs:
            spec["sshPublicKey"] = kwargs.pop("ssh_pub_key")

        if "hold_installation" in kwargs:
            spec["holdInstallation"] = kwargs.pop("hold_installation")

        if "machine_cidr" in kwargs:
            spec["networking"]["machineNetwork"] = [{"cidr": kwargs.pop("machine_cidr")}]

        if "platform_type" in kwargs:
            spec["platformType"] = kwargs.pop("platform_type")

        if "hyperthreading" in kwargs:
            self._set_hyperthreading(spec=spec, mode=kwargs.pop("hyperthreading"))

        if "load_balancer_type" in kwargs:
            spec["loadBalancer"] = {"type": kwargs.pop("load_balancer_type")}

        spec.update(kwargs)
        return spec

    def _set_hyperthreading(self, spec: Dict[str, Any], mode: str) -> None:
        # if hypethreading is not configured, let the service choose the default setup
        if not mode:
            return

        masters_mode, workers_mode = "Enabled", "Enabled"
        if mode == "none" or mode == "workers":
            masters_mode = "Disabled"
        if mode == "none" or mode == "masters":
            workers_mode = "Disabled"

        spec["controlPlane"] = {
            "hyperthreading": masters_mode,
            "name": "master",
        }
        spec["compute"] = [
            {
                "hyperthreading": workers_mode,
                "name": "worker",
            }
        ]

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def get_spec(self) -> dict:
        return self.get().get("spec") or {}

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        log.info("deleted agentclusterinstall %s", self.ref)

    def status(self, timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT) -> dict:
        def _attempt_to_get_status() -> dict:
            return self.get()["status"]

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f"cluster {self.ref} status",
            expected_exceptions=KeyError,
        )

    def wait_to_be_ready(
        self,
        ready: bool,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    ) -> None:
        return self.wait_for_condition(
            cond_type=self._requirements_met_condition_name,
            required_status=str(ready),
            timeout=timeout,
        )

    def wait_to_be_installing(
        self,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    ) -> None:
        return self.wait_for_condition(
            cond_type=self._requirements_met_condition_name,
            required_status="True",
            required_reason="ClusterAlreadyInstalling",
            timeout=timeout,
        )

    def wait_to_be_installed(
        self,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_INSTALLATION_COMPLETE_TIMEOUT,
    ) -> None:
        return self.wait_for_condition(
            cond_type=self._completed_condition_name,
            required_status="True",
            required_reason="InstallationCompleted",
            exception_status="False",
            exception_reason="InstallationFailed",
            timeout=timeout,
        )

    def wait_for_condition(
        self,
        cond_type: str,
        required_status: str,
        required_reason: Optional[str] = None,
        exception_status: Optional[str] = None,
        exception_reason: Optional[str] = None,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    ) -> None:
        log.info(
            "waiting for agentclusterinstall %s condition %s to be in status " "%s",
            self.ref,
            cond_type,
            required_status,
        )

        def _has_required_condition() -> Optional[bool]:
            status, reason, message = self.condition(cond_type=cond_type, timeout=0.5)
            log.info(
                f"waiting for condition <{cond_type}> to be in status <{required_status}>."
                f" actual status is: {status} {reason} {message}"
            )
            if status == required_status:
                if required_reason:
                    return required_reason == reason
                return True
            elif status == exception_status and reason == exception_reason:
                raise Exception(f"Unexpected status and reason: {exception_status} {exception_reason}")

        waiting.wait(
            _has_required_condition,
            timeout_seconds=timeout,
            waiting_for=f"agentclusterinstall {self.ref} condition " f"{cond_type} to be {required_status}",
            sleep_seconds=10,
            expected_exceptions=waiting.exceptions.TimeoutExpired,
        )

    def condition(
        self,
        cond_type,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        for condition in self.status(timeout).get("conditions", []):
            if cond_type == condition.get("type"):
                return condition.get("status"), condition.get("reason"), condition.get("message")

        return None, None, None

    def download_kubeconfig(self, kubeconfig_path):
        def _get_kubeconfig_secret() -> dict:
            return self.get()["spec"]["clusterMetadata"]["adminKubeconfigSecretRef"]

        secret_ref = waiting.wait(
            _get_kubeconfig_secret,
            sleep_seconds=1,
            timeout_seconds=consts.DEFAULT_WAIT_FOR_KUBECONFIG_TIMEOUT,
            expected_exceptions=KeyError,
            waiting_for=f"kubeconfig secret creation for cluster {self.ref}",
        )

        kubeconfig_data = (
            Secret(
                kube_api_client=self.crd_api.api_client,
                namespace=self._reference.namespace,
                **secret_ref,
            )
            .get()
            .data["kubeconfig"]
        )

        # Ensures kubeconfig directory exists
        dirname = os.path.dirname(kubeconfig_path)
        os.makedirs(dirname, exist_ok=True)

        with open(kubeconfig_path, "wt") as kubeconfig_file:
            kubeconfig_file.write(b64decode(kubeconfig_data).decode())

    @classmethod
    def list(cls, crd_api: CustomObjectsApi, namespace) -> List["AgentClusterInstall"]:
        resources = crd_api.list_namespaced_custom_object(
            group=consts.CRD_AGENT_INSTALL_GROUP,
            version=consts.CRD_AGENT_INSTALL_VERSION,
            plural=cls._plural,
            namespace=namespace,
        )

        return resources
