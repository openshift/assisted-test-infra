import waiting
import yaml

from typing import Optional, Union, Dict
from pprint import pformat

from kubernetes.client import ApiClient, CustomObjectsApi
from kubernetes.client.rest import ApiException

from tests.conftest import env_variables

from .global_vars import DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT
from .base_resource import BaseCustomResource
from .secret import deploy_default_secret, Secret
from .common import logger


class InstallEnv(BaseCustomResource):
    """
    InstallEnv is used to generate cluster iso.
    Image is automatically generated on CRD deployment, after InstallEnv is
    reconciled. Image download url will be exposed in the status.
    """
    _api_group = 'adi.io.my.domain'
    _api_version = 'v1alpha1'
    _plural = 'installenvs'

    def __init__(
            self,
            kube_api_client: ApiClient,
            name: str,
            namespace: str = env_variables['namespace']
    ):
        BaseCustomResource.__init__(self, name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace
        )

        logger.info(
            'created installEnv %s: %s', self.ref, pformat(yaml_data)
        )

    def create(
            self,
            cluster_deployment: 'ClusterDeployment',
            secret: Secret,
            label_selector: Optional[Dict[str, str]] = None,
            ignition_config_override: Optional[str] = None,
            **kwargs
    ) -> None:
        body = {
            'apiVersion': f'{self._api_group}/{self._api_version}',
            'kind': 'InstallEnv',
            'metadata': self.ref.as_dict(),
            'spec': {
                'clusterRef': cluster_deployment.ref.as_dict(),
                'pullSecretRef': secret.ref.as_dict(),
                'agentLabelSelector': {'matchLabels': label_selector or {}},
                'ignitionConfigOverride': ignition_config_override or ''
            }
        }
        body['spec'].update(kwargs)
        self.crd_api.create_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace
        )

        logger.info(
            'created installEnv %s: %s', self.ref, pformat(body)
        )

    def patch(
            self,
            cluster_deployment: Optional['ClusterDeployment'],
            secret: Optional[Secret],
            label_selector: Optional[Dict[str, str]] = None,
            ignition_config_override: Optional[str] = None,
            **kwargs
    ) -> None:
        body = {'spec': kwargs}

        spec = body['spec']
        if cluster_deployment:
            spec['clusterRef'] = cluster_deployment.ref.as_dict()

        if secret:
            spec['pullSecretRef'] = secret.ref.as_dict()

        if label_selector:
            spec['agentLabelSelector'] = {'matchLabels': label_selector}

        if ignition_config_override:
            spec['ignitionConfigOverride'] = ignition_config_override

        self.crd_api.patch_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body
        )

        logger.info(
            'patching installEnv %s: %s', self.ref, pformat(body)
        )

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=self._api_group,
            version=self._api_version,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace
        )

        logger.info('deleted installEnv %s', self.ref)

    def status(
            self,
            timeout: Union[int, float] = DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT
    ) -> dict:
        """
        Status is a section in the CRD that is created after registration to
        assisted service and it defines the observed state of InstallEnv.
        Since the status key is created only after resource is processed by the
        controller in the service, it might take a few seconds before appears.
        """

        def _attempt_to_get_status() -> dict:
            return self.get()['status']

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f'installEnv {self.ref} status',
            expected_exceptions=KeyError
        )


def deploy_default_installenv(
        kube_api_client: ApiClient,
        name: str,
        ignore_conflict: bool = True,
        cluster_deployment: Optional['ClusterDeployment'] = None,
        secret: Optional[Secret] = None,
        label_selector: Optional[Dict[str, str]] = None,
        ignition_config_override: Optional[str] = None,
        **kwargs
) -> InstallEnv:

    install_env = InstallEnv(kube_api_client, name)
    try:
        if 'filepath' in kwargs:
            _create_installenv_from_yaml_file(
                install_env=install_env,
                filepath=kwargs['filepath']
            )
        else:
            _create_installenv_from_attrs(
                kube_api_client=kube_api_client,
                name=name,
                ignore_conflict=ignore_conflict,
                install_env=install_env,
                cluster_deployment=cluster_deployment,
                secret=secret,
                label_selector=label_selector,
                ignition_config_override=ignition_config_override,
                **kwargs
            )
    except ApiException as e:
        if not (e.reason == 'Conflict' and ignore_conflict):
            raise

    # wait until install-env will have status (i.e until resource will be
    # processed in assisted-service).
    install_env.status()

    return install_env


def _create_installenv_from_yaml_file(
        install_env: InstallEnv,
        filepath: str
) -> None:
    with open(filepath) as fp:
        yaml_data = yaml.safe_load(fp)

    install_env.create_from_yaml(yaml_data)


def _create_installenv_from_attrs(
        kube_api_client: ApiClient,
        install_env: InstallEnv,
        cluster_deployment: 'ClusterDeployment',
        secret: Optional[Secret] = None,
        label_selector: Optional[Dict[str, str]] = None,
        ignition_config_override: Optional[str] = None,
        **kwargs
) -> None:
    if not secret:
        secret = deploy_default_secret(
            kube_api_client=kube_api_client,
            name=cluster_deployment.ref.name
        )
    install_env.create(
        cluster_deployment=cluster_deployment,
        secret=secret,
        label_selector=label_selector,
        ignition_config_override=ignition_config_override,
        **kwargs
    )
