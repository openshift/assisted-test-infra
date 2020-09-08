import os
import urllib3
import json

from kubernetes.config.kube_config import load_kube_config
from kubernetes.config.kube_config import Configuration
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


class OCConfiguration(Configuration):
    """ A kubernetes config.kube_config.Configuration object that supports both
        local and oc modes. Can be used also by kubernetes.client.APIClient. """

    def __init__(self):
        Configuration.__init__(self)
        self.__verify_ssl = False

    @property
    def token(self):
        return self.api_key['authorization']

    @token.setter
    def token(self, token):
        if not token.startswith('Bearer '):
            token = f'Bearer {token}'

        self.api_key['authorization'] = token

    @property
    def server(self):
        return self.host

    @server.setter
    def server(self, server):
        self.host = server

    @property
    def verify_ssl(self):
        return self.__verify_ssl

    @verify_ssl.setter
    def verify_ssl(self, verify_ssl):
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.__verify_ssl = verify_ssl


class OCApiClient(ApiClient):
    """ A class meant to replace kubernetes.client.APIClient for oc mode. """

    def call_api(
            self,
            resource_path,
            method,
            path_params=None,
            query_params=None,
            header_params=None,
            body=None,
            post_params=None,
            files=None,
            response_type=None,
            auth_settings=None,
            async_req=None,
            _return_http_data_only=None,
            collection_formats=None,
            _preload_content=True,
            _request_timeout=None
    ):
        if auth_settings == ['BearerToken']:
            auth_settings = self.configuration.auth_settings()

        return ApiClient.call_api(
            self,
            resource_path,
            method,
            path_params,
            query_params,
            header_params,
            body,
            post_params,
            files,
            response_type,
            auth_settings,
            async_req,
            _return_http_data_only,
            collection_formats,
            _preload_content,
            _request_timeout
        )


def get_oc_api_client(token=None, server=None, verify_ssl=False):
    config = OCConfiguration()
    load_kube_config(
        config_file=os.environ.get('KUBECONFIG'),
        client_configuration=config
    )

    if token:
        config.token = token

    if server:
        config.server = server

    config.verify_ssl = verify_ssl

    return OCApiClient(config)


def get_namespaced_service_urls_list(
        client,
        namespace,
        service=None,
        scheme='http'
        ):
    urls = []
    routes = get_namespaced_service_routes_list(client, namespace, service)
    for route in routes.items:
        for rule in _load_resource_config_dict(route)['spec']['rules']:
            if 'host' in rule:
                urls.append(scheme + '://' + rule['host'])
    return urls


def get_namespaced_service_routes_list(client, namespace, service):
    return client.call_api(
        f'/apis/route.openshift.io/v1/namespaces/{namespace}/routes',
        method='GET',
        query_params=[('fieldSelector', f'spec.to.name={service}')],
        response_type='V1ResourceQuotaList',
        auth_settings=['BearerToken'],
        _return_http_data_only=True
    )


def _load_resource_config_dict(resource):
    raw = resource.metadata.annotations[
        'kubectl.kubernetes.io/last-applied-configuration'
    ]
    return json.loads(raw)
