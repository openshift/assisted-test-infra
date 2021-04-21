import logging

from pprint import pformat
from base64 import b64decode
from typing import Optional, Union, Dict, Tuple, List, Iterable

import waiting
import yaml
from kubernetes.client import ApiClient, CustomObjectsApi
from kubernetes.client.rest import ApiException
from tests.conftest import env_variables

from .global_vars import (
    CRD_API_GROUP,
    HIVE_API_GROUP,
    HIVE_API_VERSION,
    DEFAULT_API_VIP,
    DEFAULT_API_VIP_DNS_NAME,
    DEFAULT_INGRESS_VIP,
    DEFAULT_MACHINE_CIDR,
    DEFAULT_CLUSTER_CIDR,
    DEFAULT_SERVICE_CIDR,
    FAILURE_STATES,
    DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT,
    DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
    DEFAULT_WAIT_FOR_AGENTS_TIMEOUT,
    DEFAULT_WAIT_FOR_INSTALLATION_COMPLETE_TIMEOUT,
)

from .common import does_string_contain_value, UnexpectedStateError
from .base_resource import BaseCustomResource
from .cluster_image_set import ClusterImageSetReference
from .secret import deploy_default_secret, Secret
from .agent import Agent


logger = logging.getLogger(__name__)


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
            agent_selector: Optional[Dict[str, str]] = None,
    ):
        self.api_vip = api_vip
        self.api_vip_dns_name = api_vip_dns_name
        self.ingress_vip = ingress_vip
        self.agent_selector = agent_selector

    def __repr__(self) -> str:
        return str(self.as_dict())

    def as_dict(self) -> dict:
        data = {
            'agentBareMetal': {
                'apiVIP': self.api_vip,
                'ingressVIP': self.ingress_vip,
                'agentSelector': self.agent_selector or {},
            }
        }

        if self.api_vip_dns_name:
            data['agentBareMetal']['apiVIPDNSName'] = self.api_vip_dns_name

        return data


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
    ):
        self.host_prefix = host_prefix
        self.machine_cidr = machine_cidr
        self.cluster_cidr = cluster_cidr
        self.service_cidr = service_cidr
        self.control_plane_agents = control_plane_agents
        self.worker_agents = worker_agents
        self.ssh_public_key = ssh_public_key

    def __repr__(self) -> str:
        return str(self.as_dict())

    def as_dict(self) -> dict:
        data = {
            'agent': {
                'networking': {
                    'clusterNetwork': [{
                        'cidr': self.cluster_cidr,
                        'hostPrefix': self.host_prefix,
                    }],
                    'serviceNetwork': [self.service_cidr]
                },
                'provisionRequirements': {
                    'controlPlaneAgents': self.control_plane_agents,
                    'workerAgents': self.worker_agents,
                },
            }
        }

        if does_string_contain_value(self.ssh_public_key):
            data['agent']['sshPublicKey'] = self.ssh_public_key

        if does_string_contain_value(self.machine_cidr):
            data['agent']['networking']['machineNetwork'] = [{
                'cidr': self.machine_cidr,
            }]

        return data


class ClusterDeployment(BaseCustomResource):
    """
    A CRD that represents cluster in assisted-service.
    On creation the cluster will be registered to the service.
    On deletion it will be unregistered from the service.
    When has sufficient data installation will start automatically.
    """
    _plural = 'clusterdeployments'

    def __init__(
            self,
            kube_api_client: ApiClient,
            name: str,
            namespace: str = env_variables['namespace'],
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace,
        )

        logger.info(
            'created cluster deployment %s: %s', self.ref, pformat(yaml_data)
        )

    def create(
            self,
            platform: Platform,
            install_strategy: InstallStrategy,
            secret: Secret,
            imageSetRef: ClusterImageSetReference,
            base_domain: str = env_variables['base_domain'],
            **kwargs,
    ):
        body = {
            'apiVersion': f'{HIVE_API_GROUP}/{HIVE_API_VERSION}',
            'kind': 'ClusterDeployment',
            'metadata': self.ref.as_dict(),
            'spec': {
                'clusterName': self.ref.name,
                'baseDomain': base_domain,
                'platform': platform.as_dict(),
                'provisioning': {'installStrategy': install_strategy.as_dict(), 'imageSetRef': imageSetRef.as_dict()},
                'pullSecretRef': secret.ref.as_dict(),
            }
        }
        body['spec'].update(kwargs)
        self.crd_api.create_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace,
        )

        logger.info(
            'created cluster deployment %s: %s', self.ref, pformat(body)
        )

    def patch(
            self,
            platform: Optional[Platform] = None,
            install_strategy: Optional[InstallStrategy] = None,
            secret: Optional[Secret] = None,
            **kwargs,
    ) -> None:
        body = {'spec': kwargs}

        spec = body['spec']
        if platform:
            spec['platform'] = platform.as_dict()

        if install_strategy:
            spec['provisioning'] = {
                'installStrategy': install_strategy.as_dict()
            }

        if secret:
            spec['pullSecretRef'] = secret.ref.as_dict()

        self.crd_api.patch_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        logger.info(
            'patching cluster deployment %s: %s', self.ref, pformat(body)
        )
    
    def annotate_install_config(self, install_config: str) -> None:
        body = {
            'metadata': {
                'annotations': {
                    f'{CRD_API_GROUP}/install-config-overrides': install_config
                }
            }
        }

        self.crd_api.patch_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        logger.info(
            'patching cluster install config %s: %s', self.ref, pformat(body)
        )

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=HIVE_API_GROUP,
            version=HIVE_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        logger.info('deleted cluster deployment %s', self.ref)

    def status(
            self,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT,
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
            expected_exceptions=KeyError,
        )

    def state(
            self,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
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
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT,
            *,
            raise_on_states: Iterable[str] = FAILURE_STATES,
    ) -> None:
        required_state = required_state.lower()
        raise_on_states = [x.lower() for x in raise_on_states]

        def _has_required_state() -> Optional[bool]:
            state, state_info = self.state(timeout=0.5)
            state = state.lower() if state else state
            if state == required_state:
                return True
            elif state in raise_on_states:
                raise UnexpectedStateError(
                    f'while waiting for state `{required_state}`, cluster '
                    f'{self.ref} state changed unexpectedly to `{state}`: '
                    f'{state_info}'
                )

        logger.info("Waiting till cluster will be in %s state", required_state)
        waiting.wait(
            _has_required_state,
            timeout_seconds=timeout,
            waiting_for=f'cluster {self.ref} state to be {required_state}',
            expected_exceptions=waiting.exceptions.TimeoutExpired,
        )

    def list_agents(self) -> List[Agent]:
        return Agent.list(self.crd_api, self)

    def wait_for_agents(
            self,
            num_agents: int = 1,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_AGENTS_TIMEOUT,
    ) -> List[Agent]:

        def _wait_for_sufficient_agents_number() -> List[Agent]:
            agents = self.list_agents()
            return agents if len(agents) == num_agents else []

        return waiting.wait(
            _wait_for_sufficient_agents_number,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f'cluster {self.ref} to have {num_agents} agents',
        )

    def wait_to_be_installed(
            self, 
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_INSTALLATION_COMPLETE_TIMEOUT,
    ) -> None:

        waiting.wait(
            lambda: self.get()['spec'].get('installed') is True,
            timeout_seconds=timeout,
            waiting_for=f'cluster {self.ref} state installed',
            expected_exceptions=waiting.exceptions.TimeoutExpired,
        )

    def download_kubeconfig(self, kubeconfig_path):
        def _get_kubeconfig_secret() -> dict:
            return self.get()['spec']['clusterMetadata']['adminKubeconfigSecretRef']

        secret_ref = waiting.wait(
            _get_kubeconfig_secret,
            sleep_seconds=1,
            timeout_seconds=240,
            expected_exceptions=KeyError,
            waiting_for=f'kubeconfig secret creation for cluster {self.ref}',
        )

        kubeconfig_data = Secret(
            kube_api_client=self.crd_api.api_client,
            **secret_ref,
        ).get().data['kubeconfig']

        with open(kubeconfig_path, 'wt') as kubeconfig_file:
            kubeconfig_file.write(b64decode(kubeconfig_data).decode())


def deploy_default_cluster_deployment(
        kube_api_client: ApiClient,
        name: str,
        ignore_conflict: bool = True,
        base_domain: str = env_variables['base_domain'],
        platform: Optional[Platform] = None,
        install_strategy: Optional[InstallStrategy] = None,
        secret: Optional[Secret] = None,
        **kwargs,
) -> ClusterDeployment:
    cluster_deployment = ClusterDeployment(kube_api_client, name)
    try:
        if 'filepath' in kwargs:
            _create_from_yaml_file(
                kube_api_client=kube_api_client,
                ignore_conflict=ignore_conflict,
                cluster_deployment=cluster_deployment,
                filepath=kwargs['filepath'],
            )
        else:
            _create_from_attrs(
                kube_api_client=kube_api_client,
                name=name,
                ignore_conflict=ignore_conflict,
                cluster_deployment=cluster_deployment,
                base_domain=base_domain,
                secret=secret,
                platform=platform,
                install_strategy=install_strategy,
                **kwargs,
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
        filepath: str,
) -> None:
    with open(filepath) as fp:
        yaml_data = yaml.safe_load(fp)

    deploy_default_secret(
        kube_api_client=kube_api_client,
        name=yaml_data['spec']['pullSecretRef']['name'],
        ignore_conflict=ignore_conflict,
    )
    cluster_deployment.create_from_yaml(yaml_data)


def _create_from_attrs(
        kube_api_client: ApiClient,
        name: str,
        ignore_conflict: bool,
        cluster_deployment: ClusterDeployment,
        base_domain: str,
        secret: Optional[Secret] = None,
        platform: Optional[Platform] = None,
        install_strategy: Optional[InstallStrategy] = None,
        **kwargs,
) -> None:
    if not secret:
        secret = deploy_default_secret(
            kube_api_client=kube_api_client,
            name=name,
            ignore_conflict=ignore_conflict,
        )

    cluster_deployment.create(
        platform=platform or Platform(),
        install_strategy=install_strategy or InstallStrategy(),
        secret=secret,
        base_domain=base_domain,
        **kwargs,
    )
