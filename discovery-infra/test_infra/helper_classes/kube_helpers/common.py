import logging
import warnings

from typing import Optional

from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException

from test_infra.assisted_service_api import ClientFactory
from test_infra.helper_classes.kube_helpers.idict import IDict

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

    def __init__(self, kube_api_client: Optional[ApiClient] = None,
                 clean_on_exit: Optional[bool] = True):

        self.api_client = kube_api_client
        self._clean_on_exit = clean_on_exit

    def __enter__(self):
        logger.info("entering kube api context")
        self.resources.clear()

    def __exit__(self, *_):
        logger.info("exiting kube api context")
        if self._clean_on_exit:
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

    def __init__(
        self,
        name: str,
        namespace: str,
        kind: Optional[str] = None,
        group: Optional[str] = None,
        version: Optional[str] = None,
    ):
        self.name = name
        self.namespace = namespace
        self.kind = kind
        self.group = group
        self.version = version

    def __eq__(self, other: "ObjectReference") -> bool:
        return all(
            (
                other.name == self.name,
                other.namespace == self.namespace,
                other.kind == self.kind,
                other.group == self.group,
                other.version == self.version,
            )
        )

    def as_dict(self) -> dict:
        dct = {"name": self.name, "namespace": self.namespace}
        if self.kind:
            dct["kind"] = self.kind
        if self.version:
            dct["version"] = self.version
        if self.group:
            dct["group"] = self.group
        return dct


def create_kube_api_client(kubeconfig_path: Optional[str] = None) -> ApiClient:
    warnings.warn(
        "create_kube_api_client is deprecated. Use ClientFactory.create_kube_api_client instead.", DeprecationWarning
    )
    return ClientFactory.create_kube_api_client(kubeconfig_path)
