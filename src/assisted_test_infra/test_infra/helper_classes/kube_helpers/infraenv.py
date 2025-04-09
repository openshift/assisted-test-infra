import re
import warnings
from pprint import pformat
from typing import Dict, List, Optional, Union

import waiting
import yaml
from kubernetes.client import ApiClient, CustomObjectsApi
from kubernetes.client.rest import ApiException

import consts
from service_client import log

from .agent import Agent
from .base_resource import BaseCustomResource
from .cluster_deployment import ClusterDeployment
from .idict import IDict
from .secret import Secret, deploy_default_secret

ISO_URL_PATTERN = re.compile(
    r"(?P<api_url>.+)/api/assisted-install/v1/clusters/" r"(?P<cluster_id>[0-9a-z-]+)/downloads/image"
)


class Proxy(IDict):
    """Proxy settings for the installation.

    Args:
        http_proxy (str): endpoint for accessing in every HTTP request.
        https_proxy (str): endpoint for accessing in every HTTPS request.
        no_proxy (str): comma separated values of addresses/address ranges/DNS entries
            that shouldn't be accessed via proxies.
    """

    def __init__(
        self,
        http_proxy: str,
        https_proxy: str,
        no_proxy: str,
    ):
        self.http_proxy = http_proxy
        self.https_proxy = https_proxy
        self.no_proxy = no_proxy

    def as_dict(self) -> dict:
        return {
            "httpProxy": self.http_proxy,
            "httpsProxy": self.https_proxy,
            "noProxy": self.no_proxy,
        }


class InfraEnv(BaseCustomResource):
    """
    InfraEnv is used to generate cluster iso.
    Image is automatically generated on CRD deployment, after InfraEnv is
    reconciled. Image download url will be exposed in the status.
    """

    _plural = "infraenvs"

    def __init__(
        self,
        kube_api_client: ApiClient,
        name: str,
        namespace: str = consts.DEFAULT_NAMESPACE,
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)
        self._iso_download_path = None

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace,
        )

        log.info("created infraEnv %s: %s", self.ref, pformat(yaml_data))

    def create(
        self,
        cluster_deployment: Optional[ClusterDeployment],
        secret: Secret,
        set_infraenv_version: bool = False,
        proxy: Optional[Proxy] = None,
        ignition_config_override: Optional[str] = None,
        nmstate_label: Optional[str] = None,
        ssh_pub_key: Optional[str] = None,
        additional_trust_bundle: Optional[str] = None,
        openshift_version: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        body = {
            "apiVersion": f"{consts.CRD_API_GROUP}/{consts.CRD_API_VERSION}",
            "kind": "InfraEnv",
            "metadata": self.ref.as_dict(),
            "spec": {
                "pullSecretRef": secret.ref.as_dict(),
                "nmStateConfigLabelSelector": {
                    "matchLabels": {f"{consts.CRD_API_GROUP}/selector-nmstate-config-name": nmstate_label or ""}
                },
                "ignitionConfigOverride": ignition_config_override or "",
            },
        }

        # Late-binding infra-envs don't have a clusterRef in the beginning
        if cluster_deployment is not None:
            body["spec"]["clusterRef"] = cluster_deployment.ref.as_dict()

        spec = body["spec"]
        if proxy:
            spec["proxy"] = proxy.as_dict()
        if ssh_pub_key:
            spec["sshAuthorizedKey"] = ssh_pub_key
        if additional_trust_bundle:
            spec["additionalTrustBundle"] = additional_trust_bundle

        if set_infraenv_version:
            body["spec"]["osImageVersion"] = openshift_version

        spec.update(kwargs)
        infraenv = self.crd_api.create_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace,
        )

        log.info("created infraEnv %s: %s", self.ref, pformat(body))
        return infraenv

    def patch(
        self,
        cluster_deployment: Optional[ClusterDeployment],
        secret: Optional[Secret],
        proxy: Optional[Proxy] = None,
        ignition_config_override: Optional[str] = None,
        nmstate_label: Optional[str] = None,
        ssh_pub_key: Optional[str] = None,
        additional_trust_bundle: Optional[str] = None,
        **kwargs,
    ) -> None:
        body = {"spec": kwargs}

        spec = body["spec"]
        if cluster_deployment:
            spec["clusterRef"] = cluster_deployment.ref.as_dict()

        if secret:
            spec["pullSecretRef"] = secret.ref.as_dict()

        if proxy:
            spec["proxy"] = proxy.as_dict()

        if nmstate_label:
            spec["nmStateConfigLabelSelector"] = {
                "matchLabels": {
                    f"{consts.CRD_API_GROUP}/selector-nmstate-config-name": nmstate_label,
                }
            }

        if ignition_config_override:
            spec["ignitionConfigOverride"] = ignition_config_override

        if ssh_pub_key:
            spec["sshAuthorizedKey"] = ssh_pub_key

        if additional_trust_bundle:
            spec["additionalTrustBundle"] = additional_trust_bundle

        self.crd_api.patch_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        log.info("patching infraEnv %s: %s", self.ref, pformat(body))

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        log.info("deleted infraEnv %s", self.ref)

    def status(self, timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT) -> dict:
        """
        Status is a section in the CRD that is created after registration to
        assisted service and it defines the observed state of InfraEnv.
        Since the status key is created only after resource is processed by the
        controller in the service, it might take a few seconds before appears.
        """

        def _attempt_to_get_status() -> dict:
            return self.get()["status"]

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f"infraEnv {self.ref} status",
            expected_exceptions=KeyError,
        )

    def get_iso_download_url(
        self,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_ISO_URL_TIMEOUT,
    ):
        def _attempt_to_get_image_url() -> str:
            return self.get()["status"]["isoDownloadURL"]

        return waiting.wait(
            _attempt_to_get_image_url,
            sleep_seconds=3,
            timeout_seconds=timeout,
            waiting_for="image to be created",
            expected_exceptions=KeyError,
        )

    def get_cluster_id(self):
        iso_download_url = self.get_iso_download_url()
        return ISO_URL_PATTERN.match(iso_download_url).group("cluster_id")

    @classmethod
    def deploy_default_infraenv(
        cls,
        kube_api_client: ApiClient,
        name: str,
        namespace: str,
        pull_secret: str,
        ignore_conflict: bool = True,
        cluster_deployment: Optional[ClusterDeployment] = None,
        secret: Optional[Secret] = None,
        proxy: Optional[Proxy] = None,
        ignition_config_override: Optional[str] = None,
        **kwargs,
    ) -> "InfraEnv":
        infra_env = InfraEnv(kube_api_client, name, namespace)
        try:
            if "filepath" in kwargs:
                infra_env._create_infraenv_from_yaml_file(
                    filepath=kwargs["filepath"],
                )
            else:
                infra_env._create_infraenv_from_attrs(
                    kube_api_client=kube_api_client,
                    name=name,
                    ignore_conflict=ignore_conflict,
                    pull_secret=pull_secret,
                    cluster_deployment=cluster_deployment,
                    secret=secret,
                    proxy=proxy,
                    ignition_config_override=ignition_config_override,
                    **kwargs,
                )
        except ApiException as e:
            if not (e.reason == "Conflict" and ignore_conflict):
                raise

        # wait until install-env will have status (i.e until resource will be
        # processed in assisted-service).
        infra_env.status()

        return infra_env

    def _create_infraenv_from_yaml_file(
        self,
        filepath: str,
    ) -> None:
        with open(filepath) as fp:
            yaml_data = yaml.safe_load(fp)

        self.create_from_yaml(yaml_data)

    def _create_infraenv_from_attrs(
        self,
        kube_api_client: ApiClient,
        cluster_deployment: ClusterDeployment,
        pull_secret: str,
        secret: Optional[Secret] = None,
        proxy: Optional[Proxy] = None,
        ignition_config_override: Optional[str] = None,
        additional_trust_bundle: Optional[str] = None,
        **kwargs,
    ) -> None:
        if not secret:
            secret = deploy_default_secret(
                kube_api_client=kube_api_client,
                name=cluster_deployment.ref.name,
                namespace=self._reference.namespace,
                pull_secret=pull_secret,
            )
        self.create(
            cluster_deployment=cluster_deployment,
            secret=secret,
            proxy=proxy,
            ignition_config_override=ignition_config_override,
            additional_trust_bundle=additional_trust_bundle,
            **kwargs,
        )

    def list_agents(self) -> List[Agent]:
        all_agents = self.crd_api.list_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=Agent._plural,
            namespace=self.ref.namespace,
        ).get("items", [])

        return [
            Agent(
                kube_api_client=self.crd_api.api_client,
                name=agent["metadata"]["name"],
                namespace=agent["metadata"]["namespace"],
            )
            for agent in all_agents
            if agent["metadata"]["labels"].get("infraenvs.agent-install.openshift.io") == self.ref.name
        ]

    def wait_for_agents(
        self,
        num_agents: int = 1,
        timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_AGENTS_TIMEOUT,
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


def deploy_default_infraenv(
    kube_api_client: ApiClient,
    name: str,
    namespace: str,
    pull_secret: str,
    ignore_conflict: bool = True,
    cluster_deployment: Optional[ClusterDeployment] = None,
    secret: Optional[Secret] = None,
    proxy: Optional[Proxy] = None,
    ignition_config_override: Optional[str] = None,
    additional_trust_bundle: Optional[str] = None,
    **kwargs,
) -> "InfraEnv":
    warnings.warn(
        "deploy_default_infraenv is deprecated. Use InfraEnv.deploy_default_infraenv instead.", DeprecationWarning
    )

    return InfraEnv.deploy_default_infraenv(
        kube_api_client,
        name,
        namespace,
        pull_secret,
        ignore_conflict,
        cluster_deployment,
        secret,
        proxy,
        ignition_config_override,
        additional_trust_bundle,
        **kwargs,
    )
