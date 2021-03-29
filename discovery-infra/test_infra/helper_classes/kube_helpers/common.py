import logging

from typing import Optional

from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException
from kubernetes.config import load_kube_config
from kubernetes.config.kube_config import Configuration


# silence kubernetes debug messages.
logging.getLogger('kubernetes').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


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
        logger.info('entering kube api context')
        self.resources.clear()

    def __exit__(self, *_):
        logger.info('exiting kube api context')
        delete_all_resources(self)


class ObjectReference:
    """
    A class that contains the information required to let you locate a
    referenced Kube API resource.
    """

    def __init__(self, name: str, namespace: str):
        self.name = name
        self.namespace = namespace

    def __repr__(self) -> str:
        return str(self.as_dict())

    def __eq__(self, other: 'ObjectReference') -> bool:
        return other.name == self.name and other.namespace == self.namespace

    def as_dict(self) -> dict:
        return {'name': self.name, 'namespace': self.namespace}


def create_kube_api_client(kubeconfig_path: Optional[str] = None) -> ApiClient:
    logger.info('creating kube client with config file: %s', kubeconfig_path)

    conf = Configuration()
    load_kube_config(config_file=kubeconfig_path, client_configuration=conf)
    return ApiClient(configuration=conf)


def delete_all_resources(
        kube_api_context: KubeAPIContext,
        ignore_not_found: bool = True
) -> None:
    logger.info('deleting all resources')

    for resource in kube_api_context.resources:
        try:
            resource.delete()
        except ApiException as e:
            if not (e.reason == 'Not Found' and ignore_not_found):
                raise


def does_string_contain_value(s: Optional[str]) -> bool:
    return s and s != '""'

