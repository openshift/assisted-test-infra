import logging
import warnings

from typing import Optional

from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException

from test_infra.assisted_service_api import ClientFactory
from test_infra.helper_classes.kube_helpers.idict import IDict
from tests.conftest import env_variables

# silence kubernetes debug messages.
logging.getLogger("kubernetes").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


class UnexpectedStateError(Exception):
    pass


class KubeAPIContext:
    """
    This class is used to hold information shared between both kubernetes and
    custom resources. It provides a contextmanager responsible for cleanup of
    all the resources created within it.
    """

    resources = set()

    def __init__(self, kube_api_client: Optional[ApiClient] = None):
        self.api_client = kube_api_client

    def __enter__(self):
        logger.info("entering kube api context")
        self.resources.clear()

    def __exit__(self, *_):
        logger.info("exiting kube api context")
        self._delete_all_resources()

    def _delete_all_resources(self, ignore_not_found: bool = True) -> None:
        logger.info("deleting all resources")

        for resource in self.resources:
            try:
                resource.delete()
            except ApiException as e:
                if not (e.reason == "Not Found" and ignore_not_found):
                    raise


class ObjectReference(IDict):
    """
    A class that contains the information required to let you locate a
    referenced Kube API resource.
    """

    def __init__(self, name: str, namespace: str):
        self.name = name
        self.namespace = namespace

    def __eq__(self, other: "ObjectReference") -> bool:
        return other.name == self.name and other.namespace == self.namespace

    def as_dict(self) -> dict:
        return {"name": self.name, "namespace": self.namespace}


def create_kube_api_client(kubeconfig_path: Optional[str] = None) -> ApiClient:
    warnings.warn("create_kube_api_client is deprecated. Use ClientFactory.create_kube_api_client instead.",
                  DeprecationWarning)
    return ClientFactory.create_kube_api_client(kubeconfig_path or env_variables["installer_kubeconfig_path"])


def does_string_contain_value(s: Optional[str]) -> bool:
    return s and s != '""'
