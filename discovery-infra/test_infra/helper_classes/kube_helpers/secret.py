import logging
import os
import json
import warnings

from typing import Optional

from kubernetes.client import ApiClient, CoreV1Api
from kubernetes.client.rest import ApiException

from tests.conftest import env_variables

from .base_resource import BaseResource


logger = logging.getLogger(__name__)


class Secret(BaseResource):
    """
    A Kube API secret resource that consists of the pull secret data, used
    by a ClusterDeployment CRD.
    """

    _secret_type = "kubernetes.io/dockerconfigjson"
    _docker_config_json_key = ".dockerconfigjson"

    def __init__(self, kube_api_client: ApiClient, name: str, namespace: str = env_variables["namespace"]):
        super().__init__(name, namespace)
        self.v1_api = CoreV1Api(kube_api_client)

    def create(self, pull_secret: str = env_variables["pull_secret"]):
        self.v1_api.create_namespaced_secret(
            body={
                "type": self._secret_type,
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": self.ref.as_dict(),
                "stringData": {self._docker_config_json_key: pull_secret},
            },
            namespace=self.ref.namespace,
        )

        logger.info("created secret %s", self.ref)

    def delete(self) -> None:
        self.v1_api.delete_namespaced_secret(name=self.ref.name, namespace=self.ref.namespace)

        logger.info("deleted secret %s", self.ref)

    def get(self) -> dict:
        return self.v1_api.read_namespaced_secret(
            name=self.ref.name,
            namespace=self.ref.namespace,
            pretty=True,
        )

    @classmethod
    def deploy_default_secret(
        cls, kube_api_client: ApiClient, name: str, pull_secret: str, ignore_conflict: bool = True
    ) -> "Secret":
        cls._validate_pull_secret(pull_secret)
        secret = Secret(kube_api_client, name)
        try:
            secret.create(pull_secret)
        except ApiException as e:
            if not (e.reason == "Conflict" and ignore_conflict):
                raise
        return secret

    @staticmethod
    def _validate_pull_secret(pull_secret: str) -> None:
        if not pull_secret:
            return
        try:
            json.loads(pull_secret)
        except json.JSONDecodeError:
            raise ValueError(f"invalid pull secret {pull_secret}")


def deploy_default_secret(
    kube_api_client: ApiClient, name: str, ignore_conflict: bool = True, pull_secret: Optional[str] = None
) -> Secret:
    warnings.warn("deploy_default_secret is deprecated. Use Secret.deploy_default_secret instead."
                  "Note that pull_secret argument is now mandatory.", DeprecationWarning)
    if pull_secret is None:
        pull_secret = os.environ.get("PULL_SECRET", "")
    return Secret.deploy_default_secret(kube_api_client, name, pull_secret, ignore_conflict)
