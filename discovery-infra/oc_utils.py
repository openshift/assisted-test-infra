import os
import urllib3

from kubernetes.config import kube_config
from kubernetes.client import ApiClient


def extend_parser_with_oc_arguments(parser):
    parser.add_argument(
        '--oc-mode',
        help='If set, use oc instead of minikube',
        action='store_true',
        default=False
    )
    parser.add_argument(
        '-oct',
        '--oc-token',
        help='Token for oc login (an alternative for --oc-user & --oc-pass)',
        type=str,
        default='http'
    )
    parser.add_argument(
        '-ocs',
        '--oc-server',
        help='Server for oc login, required if --oc-token is provided',
        type=str,
        default='https://api.ocp.prod.psi.redhat.com:6443'
    )
    parser.add_argument(
        '--oc-scheme',
        help='Scheme for assisted-service url on oc',
        type=str,
        default='http'
    )


class OC(object):

    KUBE_CONFIG_PATH = os.environ.get('KUBECONFIG')
    OC_DOMAIN = 'redhat.com'

    def __init__(self, **kwargs):
        self.config = None
        self.load_kube_config(**kwargs)
        self.client = ApiClient(self.config)

    def load_kube_config(self, token=None, server=None, verify_ssl=False):
        kube_config.load_kube_config(self.KUBE_CONFIG_PATH)
        self.config = kube_config.Configuration()
        if token:
            self.config.api_key['authorization'] = f'Bearer {token}'
        if server:
            self.config.host = server

        self.config.verify_ssl = verify_ssl
        if not self.config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.validate_conn_params()

    def validate_conn_params(self):
        if self.OC_DOMAIN not in self.config.host:
            raise ValueError('oc host is not part of the domain')

        elif not self.config.auth_settings()['BearerToken']['value']:
            raise ValueError('oc missing authentication token')
