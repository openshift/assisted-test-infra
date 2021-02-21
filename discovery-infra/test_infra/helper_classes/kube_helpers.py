"""
kube_helpers.py provides infra to deploy, manage and install cluster using
CRDs instead of restful API calls.

Simplest use of this infra is performed by calling cluster_deployment_context
fixture. With this context manager you will be able to manage a cluster
without need to handle registration and deregistration.

Example of usage:

with cluster_deployment_context(kube_api_client) as cluster_deployment:
    print(cluster_deployment.status())

When a ClusterDeployment has sufficient data, installation will be started
automatically.
"""

import logging
import os
import abc
import contextlib
import json
import yaml

import waiting

from pprint import pformat
from typing import Optional, Union, Dict, Tuple, ContextManager

from kubernetes.config import load_kube_config
from kubernetes.config.kube_config import Configuration
from kubernetes.client import ApiClient, CoreV1Api, CustomObjectsApi
from kubernetes.client.rest import ApiException

from tests.conftest import env_variables
from test_infra.utils import get_random_name


# silence kubernetes debug messages.
logging.getLogger('kubernetes').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def create_kube_api_client(kubeconfig_path: Optional[str] = None) -> ApiClient:
    logger.info('creating kube client with config file: %s', kubeconfig_path)

    conf = Configuration()
    load_kube_config(config_file=kubeconfig_path, client_configuration=conf)
    return ApiClient(configuration=conf)


def _does_string_contain_value(s: Union[str, None]) -> bool:
    return s and s != '""'


class ObjectReference:
    """
    A class that contains the information required to to let you locate a
    referenced Kube API resource.
    """
    def __init__(self, name: str, namespace: str):
        self.name = name
        self.namespace = namespace

    def __repr__(self) -> str:
        return str(self.as_dict())

    def as_dict(self) -> dict:
        return {'name': self.name, 'namespace': self.namespace}


class Secret:
    """
    A Kube API secret resource that consists of the pull secret data, used
    by a ClusterDeployment CRD.
    """
    def __init__(
            self,
            kube_api_client: ApiClient,
            name: str,
            namespace: str = env_variables['namespace']
    ):
        self.v1_api = CoreV1Api(kube_api_client)
        self._reference = ObjectReference(name=name, namespace=namespace)

    @property
    def ref(self) -> ObjectReference:
        return self._reference

    def create(self, pull_secret: str = env_variables['pull_secret']) -> None:
        self.v1_api.create_namespaced_secret(
            body={
                'apiVersion': 'v1',
                'kind': 'Secret',
                'metadata': self.ref.as_dict(),
                'stringData': {'pullSecret': pull_secret}
            },
            namespace=self.ref.namespace
        )

        logger.info('created secret %s', self.ref)

    def delete(self) -> None:
        self.v1_api.delete_namespaced_secret(
            name=self.ref.name,
            namespace=self.ref.namespace
        )

        logger.info('deleted secret %s', self.ref)


class BaseCustomResource(abc.ABC):
    """
    Base class for all CRDs, enforces basic methods that every resource must
    have e.g create, path, get, delete and status.
    """
    def __init__(self,  name: str, namespace: str):
        self._reference = ObjectReference(name=name, namespace=namespace)

    @property
    def ref(self) -> ObjectReference:
        return self._reference

    @abc.abstractmethod
    def create(self, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def patch(self, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def get(self) -> dict:
        pass

    @abc.abstractmethod
    def delete(self) -> None:
        pass

    @abc.abstractmethod
    def status(self, timeout: Union[int, float]) -> dict:
        pass


DEFAULT_API_VIP = env_variables.get('api_vip', '')
DEFAULT_API_VIP_DNS_NAME = env_variables.get('api_vip_dns_name', '')
DEFAULT_INGRESS_VIP = env_variables.get('ingress_vip', '')


class Platform:
    """
    A class that represents the configuration for the specific platform upon
    which to perform the installation.
    """
    def __init__(
            self,
            api_vip: str = DEFAULT_API_VIP,
            api_vip_dns_name: str = DEFAULT_API_VIP_DNS_NAME,
            ingress_vip: str = DEFAULT_INGRESS_VIP,
            vip_dhcp_allocation: bool = env_variables['vip_dhcp_allocation']
    ):
        self.api_vip = api_vip
        self.api_vip_dns_name = api_vip_dns_name
        self.ingress_vip = ingress_vip
        self.vip_dhcp_allocation = vip_dhcp_allocation

    def __repr__(self) -> str:
        return str(self.as_dict())

    def as_dict(self) -> dict:
        vip_dhcp_allocation = 'Enabled' if self.vip_dhcp_allocation else ''
        data = {
            'agentBareMetal': {
                'apiVIP': self.api_vip,
                'ingressVIP': self.ingress_vip,
                'VIPDHCPAllocation': vip_dhcp_allocation
            }
        }

        if self.api_vip_dns_name:
            data['agentBareMetal']['apiVIPDNSName'] = self.api_vip_dns_name

        return data


DEFAULT_MACHINE_CIDR = env_variables.get('machine_cidr', '')
DEFAULT_CLUSTER_CIDR = env_variables.get('cluster_cidr', '172.30.0.0/16')
DEFAULT_SERVICE_CIDR = env_variables.get('service_cidr', '10.128.0.0/14')


class InstallStrategy:
    """
    A class that provides platform agnostic configuration for the use of
    alternate install strategies.
    """
    def __init__(
            self,
            host_prefix: int = env_variables['host_prefix'],
            machine_cidr: str = DEFAULT_MACHINE_CIDR,
            cluster_cidr: str = DEFAULT_CLUSTER_CIDR,
            service_cidr: str = DEFAULT_SERVICE_CIDR,
            ssh_public_key: str = env_variables['ssh_public_key'],
            control_plane_agents: int = 1,
            worker_agents: int = 0,
            label_selector: Optional[Dict[str, str]] = None
    ):
        self.host_prefix = host_prefix
        self.machine_cidr = machine_cidr
        self.cluster_cidr = cluster_cidr
        self.service_cidr = service_cidr
        self.control_plane_agents = control_plane_agents
        self.worker_agents = worker_agents
        self.label_selector = label_selector
        self.ssh_public_key = ssh_public_key

    def __repr__(self) -> str:
        return str(self.as_dict())

    def as_dict(self) -> dict:
        data = {
            'agent': {
                'networking': {
                    'clusterNetwork': [{
                        'cidr': self.cluster_cidr,
                        'hostPrefix': self.host_prefix
                    }],
                    'serviceNetwork': [self.service_cidr]
                },
                'provisionRequirements': {
                    'controlPlaneAgents': self.control_plane_agents,
                    'workerAgents': self.worker_agents,
                },
                'agentSelector': {'matchLabels': self.label_selector or {}}
            }
        }

        if _does_string_contain_value(self.ssh_public_key):
            data['agent']['sshPublicKey'] = self.ssh_public_key

        if _does_string_contain_value(self.machine_cidr):
            data['agent']['networking']['machineNetwork'] = [{
                'cidr': self.machine_cidr
            }]

        return data


DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT = 60
DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT = 300


class ClusterDeployment(BaseCustomResource):
    """
    A CRD that represents cluster in assisted-service.
    On creation the cluster will be registered to the service.
    On deletion it will be unregistered from the service.
    When has sufficient data installation will start automatically.
    """

    _hive_api_group = 'hive.openshift.io'
    _plural = 'clusterdeployments'

    def __init__(
            self,
            kube_api_client: ApiClient,
            name: str,
            namespace: str = env_variables['namespace']
    ):
        BaseCustomResource.__init__(self, name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)
        self._assigned_secret = None

    @property
    def secret(self) -> Secret:
        return self._assigned_secret

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=self._hive_api_group,
            version='v1',
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace
        )
        secret_ref = yaml_data['spec']['pullSecretRef']
        self._assigned_secret = Secret(
            kube_api_client=self.crd_api.api_client,
            name=secret_ref['name'],
        )

        logger.info(
            'created cluster deployment %s: %s', self.ref, pformat(yaml_data)
        )

    def create(
            self,
            platform: Platform,
            install_strategy: InstallStrategy,
            secret: Secret,
            base_domain: str = env_variables['base_domain'],
            **kwargs
    ) -> None:
        body = {
            'apiVersion': f'{self._hive_api_group}/v1',
            'kind': 'ClusterDeployment',
            'metadata': self.ref.as_dict(),
            'spec': {
                'clusterName': self.ref.name,
                'baseDomain': base_domain,
                'platform': platform.as_dict(),
                'provisioning': {'installStrategy': install_strategy.as_dict()},
                'pullSecretRef': secret.ref.as_dict(),
            }
        }
        body['spec'].update(kwargs)
        self.crd_api.create_namespaced_custom_object(
            group=self._hive_api_group,
            version='v1',
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace
        )
        self._assigned_secret = secret

        logger.info(
            'created cluster deployment %s: %s', self.ref, pformat(body)
        )

    def patch(
            self,
            platform: Optional[Platform] = None,
            install_strategy: Optional[InstallStrategy] = None,
            secret: Optional[Secret] = None,
            **kwargs
    ) -> None:
        body = {'spec': kwargs}

        spec = body['spec']
        if platform:
            spec['platform'] = platform.as_dict()

        if install_strategy:
            spec['provisioning']['installStrategy'] = install_strategy.as_dict()

        if secret:
            spec['pullSecretRef'] = secret.ref.as_dict()

        self.crd_api.patch_namespaced_custom_object(
            group=self._hive_api_group,
            version='v1',
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body
        )

        logger.info(
            'patching cluster deployment %s: %s', self.ref, pformat(body)
        )

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=self._hive_api_group,
            version='v1',
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=self._hive_api_group,
            version='v1',
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

        logger.info('deleted cluster deployment %s', self.ref)

    def status(
            self,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT
    ) -> dict:
        """
        Status is a section in the CRD that is created after registration to
        assisted service and it defines the observed state of ClusterDeployment.
        Since the status key is created only after resource is processed by the
        controller in the service, it might take a few seconds before appears.
        """
        def _attempt_to_get_status() -> dict:
            return self.get()['status']

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f'cluster {self.ref} status',
            expected_exceptions=KeyError
        )

    def state(
            self,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT
    ) -> Tuple[str, str]:
        state, state_info = None, None
        for condition in self.status(timeout).get('conditions', []):
            reason = condition.get('reason')

            if reason == 'AgentPlatformState':
                state = condition.get('message')
            elif reason == 'AgentPlatformStateInfo':
                state_info = condition.get('message')

            if state and state_info:
                break

        return state, state_info

    def wait_for_state(
            self,
            required_state: str,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT
    ) -> None:
        required_state = required_state.lower()

        def _has_required_state() -> bool:
            state, _ = self.state(timeout=0.5)
            return state.lower() == required_state

        waiting.wait(
            _has_required_state,
            timeout_seconds=timeout,
            waiting_for=f'cluster {self.ref} state to be {required_state}',
            expected_exceptions=waiting.exceptions.TimeoutExpired
        )


def deploy_default_secret(
        kube_api_client: ApiClient,
        name: str,
        ignore_conflict: bool = True,
        pull_secret: Optional[str] = None
) -> Secret:
    if pull_secret is None:
        pull_secret = os.environ.get('PULL_SECRET', '')
    _validate_pull_secret(pull_secret)
    secret = Secret(kube_api_client, name)
    try:
        secret.create(pull_secret)
    except ApiException as e:
        if e.reason != 'Conflict' or not ignore_conflict:
            raise
    return secret


def _validate_pull_secret(pull_secret: str) -> None:
    if not pull_secret:
        return
    try:
        json.loads(pull_secret)
    except json.JSONDecodeError:
        raise ValueError(f'invalid pull secret {pull_secret}')


def deploy_default_cluster_deployment(
        kube_api_client: ApiClient,
        name: str,
        ignore_conflict: bool = True,
        base_domain: str = env_variables['base_domain'],
        platform_params: Optional[dict] = None,
        install_strategy_params: Optional[dict] = None,
        secret: Optional[Secret] = None,
        **kwargs
) -> ClusterDeployment:

    cluster_deployment = ClusterDeployment(kube_api_client, name)
    try:
        if 'filepath' in kwargs:
            _create_from_yaml_file(
                kube_api_client=kube_api_client,
                ignore_conflict=ignore_conflict,
                cluster_deployment=cluster_deployment,
                filepath=kwargs['filepath'])
        else:
            _create_from_attrs(
                kube_api_client=kube_api_client,
                name=name,
                ignore_conflict=ignore_conflict,
                cluster_deployment=cluster_deployment,
                base_domain=base_domain,
                secret=secret,
                platform_params=platform_params,
                install_strategy_params=install_strategy_params,
                **kwargs
            )
    except ApiException as e:
        if not (e.reason == 'Conflict' and ignore_conflict):
            raise

    # wait until cluster will have status (i.e until resource will be
    # processed in assisted-service).
    cluster_deployment.status()

    return cluster_deployment


def _create_from_yaml_file(
        kube_api_client: ApiClient,
        ignore_conflict: bool,
        cluster_deployment: ClusterDeployment,
        filepath: str
) -> None:
    with open(filepath) as fp:
        yaml_data = yaml.safe_load(fp)

    deploy_default_secret(
        kube_api_client=kube_api_client,
        name=yaml_data['spec']['pullSecretRef']['name'],
        ignore_conflict=ignore_conflict
    )
    cluster_deployment.create_from_yaml(yaml_data)


def _create_from_attrs(
        kube_api_client: ApiClient,
        name: str,
        ignore_conflict: bool,
        cluster_deployment: ClusterDeployment,
        base_domain: str,
        secret: Secret,
        platform_params: Optional[dict] = None,
        install_strategy_params: Optional[dict] = None,
        **kwargs
) -> None:
    if secret is None:
        secret = deploy_default_secret(
            kube_api_client=kube_api_client,
            name=name,
            ignore_conflict=ignore_conflict
        )

    platform = Platform(**platform_params or {})
    install_strategy = InstallStrategy(**install_strategy_params or {})
    cluster_deployment.create(
        platform=platform,
        install_strategy=install_strategy,
        secret=secret,
        base_domain=base_domain,
        **kwargs
    )


def delete_cluster_deployment(
        cluster_deployment: ClusterDeployment,
        ignore_not_found: bool = True
) -> None:
    def _try_to_delete_resource(
            resource: Union[Secret, ClusterDeployment]
    ) -> None:
        try:
            resource.delete()
        except ApiException as e:
            if not (e.reason == 'Not Found' and ignore_not_found):
                raise

    if cluster_deployment.secret:
        _try_to_delete_resource(cluster_deployment.secret)

    _try_to_delete_resource(cluster_deployment)


@contextlib.contextmanager
def cluster_deployment_context(
        kube_api_client: ApiClient,
        name: Optional[str] = None,
        **kwargs
) -> ContextManager[ClusterDeployment]:
    """
    Used by tests as pytest fixture, this contextmanager function yields a
    ClusterDeployment CRD that is deployed and registered to assisted service,
    alongside to a Secret resource.
    When exiting context the resources are deleted and deregistered from the
    service.
    """
    if not name:
        name = get_random_name(length=8)

    cluster_deployment = deploy_default_cluster_deployment(
        kube_api_client,
        name,
        **kwargs
    )
    try:
        yield cluster_deployment
    finally:
        delete_cluster_deployment(cluster_deployment)
