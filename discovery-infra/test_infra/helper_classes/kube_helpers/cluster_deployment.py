from pprint import pformat
from typing import Optional, Union, Dict, Tuple, List

import waiting
import yaml
from kubernetes.client import ApiClient, CustomObjectsApi
from kubernetes.client.rest import ApiException
from tests.conftest import env_variables


from .common import logger, does_string_contain_value
from .base_resource import BaseCustomResource
from .secret import deploy_default_secret, Secret
from .agent import Agent


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

        if does_string_contain_value(self.ssh_public_key):
            data['agent']['sshPublicKey'] = self.ssh_public_key

        if does_string_contain_value(self.machine_cidr):
            data['agent']['networking']['machineNetwork'] = [{
                'cidr': self.machine_cidr
            }]

        return data


DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT = 60
DEFAULT_WAIT_FOR_CRD_STATE_TIMEOUT = 300
DEFAULT_WAIT_FOR_AGENTS_TIMEOUT = 60


class ClusterDeployment(BaseCustomResource):
    """
    A CRD that represents cluster in assisted-service.
    On creation the cluster will be registered to the service.
    On deletion it will be unregistered from the service.
    When has sufficient data installation will start automatically.
    """

    _hive_api_group = 'hive.openshift.io'
    _version = 'v1'
    _plural = 'clusterdeployments'

    def __init__(
            self,
            kube_api_client: ApiClient,
            name: str,
            namespace: str = env_variables['namespace']
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=self._hive_api_group,
            version=self._version,
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace
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
            'apiVersion': f'{self._hive_api_group}/{self._version}',
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
            version=self._version,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace
        )

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
            spec['provisioning'] = {
                'installStrategy': install_strategy.as_dict()
            }

        if secret:
            spec['pullSecretRef'] = secret.ref.as_dict()

        self.crd_api.patch_namespaced_custom_object(
            group=self._hive_api_group,
            version=self._version,
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
            version=self._version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=self._hive_api_group,
            version=self._version,
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

    def list_agents(self) -> List[Agent]:
        return Agent.list(self.crd_api, self)

    def wait_for_agents(
            self,
            num_agents: int = 1,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_AGENTS_TIMEOUT
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
