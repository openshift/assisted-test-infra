import logging

from typing import Optional, Union

from kubernetes.client import ApiClient
from kubernetes.config import load_kube_config
from kubernetes.config.kube_config import Configuration


# silence kubernetes debug messages.
logging.getLogger('kubernetes').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


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


def does_string_contain_value(s: Union[str, None]) -> bool:
    return s and s != '""'
