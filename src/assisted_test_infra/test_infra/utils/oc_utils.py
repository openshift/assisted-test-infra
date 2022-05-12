import json
import os
import subprocess
from typing import Any, Dict, List, Optional

import urllib3
from kubernetes.client import ApiClient
from kubernetes.config.kube_config import Configuration, load_kube_config

OC_PATH = "/usr/local/bin/oc"


def extend_parser_with_oc_arguments(parser):
    parser.add_argument("--oc-mode", help="If set, use oc instead of minikube", action="store_true", default=False)
    parser.add_argument(
        "-oct",
        "--oc-token",
        help="Token for oc login (an alternative for --oc-user & --oc-pass)",
        type=str,
        default="http",
    )
    parser.add_argument(
        "-ocs",
        "--oc-server",
        help="Server for oc login, required if --oc-token is provided",
        type=str,
        default="https://api.ocp.prod.psi.redhat.com:6443",
    )
    parser.add_argument("--oc-scheme", help="Scheme for assisted-service url on oc", type=str, default="http")


class OCConfiguration(Configuration):
    """A kubernetes config.kube_config.Configuration object that supports both
    local and oc modes. Can be used also by kubernetes.client.APIClient."""

    def __init__(self):
        Configuration.__init__(self)
        self.__verify_ssl = False

    @property
    def token(self):
        return self.api_key["authorization"]

    @token.setter
    def token(self, token):
        if not token.startswith("Bearer "):
            token = f"Bearer {token}"

        self.api_key["authorization"] = token

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
    """A class meant to replace kubernetes.client.APIClient for oc mode."""

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
        _request_timeout=None,
        _host=None,
    ):
        if auth_settings == ["BearerToken"]:
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
            _request_timeout,
            _host=_host,
        )


def get_oc_api_client(token=None, server=None, verify_ssl=False):
    config = OCConfiguration()
    load_kube_config(config_file=os.environ.get("KUBECONFIG"), client_configuration=config)

    if token:
        config.token = token

    if server:
        config.server = server

    config.verify_ssl = verify_ssl

    return OCApiClient(config)


def get_namespaced_service_urls_list(client, namespace, service=None, scheme="http"):
    urls = []
    routes = get_namespaced_service_routes_list(client, namespace, service)
    for route in routes.items:
        for rule in _load_resource_config_dict(route)["spec"]["rules"]:
            if "host" in rule:
                urls.append(scheme + "://" + rule["host"])
    return urls


def get_namespaced_service_routes_list(client, namespace, service):
    return client.call_api(
        f"/apis/route.openshift.io/v1/namespaces/{namespace}/routes",
        method="GET",
        query_params=[("fieldSelector", f"spec.to.name={service}")],
        response_type="V1ResourceQuotaList",
        auth_settings=["BearerToken"],
        _return_http_data_only=True,
    )


def _load_resource_config_dict(resource):
    raw = resource.metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]
    return json.loads(raw)


def oc_list(kubeconfig_path: str, resource: str, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Runs `oc get <resource_name> [-n namespace] -ojson` and returns the
    deserialized contents of result["items"].
    e.g.: oc_list("node") returns [{... node dict}, {... node dict}, ...]
    May raise SubprocessError
    """
    command = [OC_PATH, "--kubeconfig", kubeconfig_path, "get", resource, "-o", "json"]

    if namespace is not None:
        command += ["--namespace", namespace]

    return json.loads(subprocess.check_output(command))["items"]


def _has_condition(resource: str, type: str, status: str) -> bool:
    """
    Checks if any of a resource's conditions matches type `type` and has status set to `status`:
    example usage: _has_condition(resource=node, type="Ready", status="True")
    """
    return any(
        condition["status"] == status
        for condition in resource["status"].get("conditions", [])
        if condition["type"] == type
    )


def get_clusteroperators_status(kubeconfig_path: str) -> Dict[str, bool]:
    """
    Returns a dict with clusteroperator names as keys and availability condition as boolean values.
    e.g.: {"etcd": True, "authentication": False}
    May raise SubprocessError
    """
    return {
        clusteroperator["metadata"]["name"]: _has_condition(resource=clusteroperator, type="Available", status="True")
        for clusteroperator in oc_list(kubeconfig_path, "clusteroperators")
    }


def get_nodes_readiness(kubeconfig_path: str) -> Dict[str, bool]:
    """
    Returns a dict with node names as keys and readiness as boolean values:
    e.g.: {"test-infra-cluster-master-0": True, "test-infra-cluster-worker-0": False}
    May raise SubprocessError
    """
    return {
        node["metadata"]["name"]: _has_condition(resource=node, type="Ready", status="True")
        for node in oc_list(kubeconfig_path, "nodes")
    }


def get_unapproved_csr_names(kubeconfig_path: str) -> List[str]:
    """
    Returns a list of names of  all CertificateSigningRequest resources which
    are unapproved.
    May raise SubprocessError
    """
    return [
        csr["metadata"]["name"]
        for csr in oc_list(kubeconfig_path, "csr")
        if not _has_condition(resource=csr, type="Approved", status="True")
    ]


def approve_csr(kubeconfig_path: str, csr_name: str):
    subprocess.check_call([OC_PATH, "--kubeconfig", kubeconfig_path, "adm", "certificate", "approve", csr_name])
