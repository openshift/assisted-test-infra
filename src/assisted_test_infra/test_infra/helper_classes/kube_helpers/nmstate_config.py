from pprint import pformat
from typing import Optional, Union

import waiting
from kubernetes.client import ApiClient, CustomObjectsApi

import consts
from service_client import log

from .base_resource import BaseCustomResource


class NMStateConfig(BaseCustomResource):
    """Configure nmstate (static IP) related settings for agents."""

    _plural = "nmstateconfigs"

    def __init__(
        self,
        kube_api_client: ApiClient,
        name: str,
        namespace: str = consts.DEFAULT_NAMESPACE,
    ):
        super().__init__(name, namespace)
        self.crd_api = CustomObjectsApi(kube_api_client)

    def create_from_yaml(self, yaml_data: dict) -> None:
        self.crd_api.create_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            body=yaml_data,
            namespace=self.ref.namespace,
        )

        log.info("created nmstate config %s: %s", self.ref, pformat(yaml_data))

    def create(
        self,
        config: dict,
        interfaces: list,
        label: Optional[str] = None,
        **kwargs,
    ) -> None:
        body = {
            "apiVersion": f"{consts.CRD_API_GROUP}/{consts.CRD_API_VERSION}",
            "kind": "NMStateConfig",
            "metadata": {
                "labels": {
                    f"{consts.CRD_API_GROUP}/selector-nmstate-config-name": label,
                },
                **self.ref.as_dict(),
            },
            "spec": {
                "config": config,
                "interfaces": interfaces,
            },
        }
        body["spec"].update(kwargs)
        self.crd_api.create_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            body=body,
            namespace=self.ref.namespace,
        )

        log.info("created nmstate config %s: %s", self.ref, pformat(body))

    def patch(
        self,
        config: dict,
        interfaces: list,
        **kwargs,
    ) -> None:
        body = {"spec": kwargs}

        spec = body["spec"]
        if config:
            spec["config"] = config

        if interfaces:
            spec["interfaces"] = interfaces

        self.crd_api.patch_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
            body=body,
        )

        log.info("patching nmstate config %s: %s", self.ref, pformat(body))

    def get(self) -> dict:
        return self.crd_api.get_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

    def delete(self) -> None:
        self.crd_api.delete_namespaced_custom_object(
            group=consts.CRD_API_GROUP,
            version=consts.CRD_API_VERSION,
            plural=self._plural,
            name=self.ref.name,
            namespace=self.ref.namespace,
        )

        log.info("deleted nmstate config %s", self.ref)

    def status(self, timeout: Union[int, float] = consts.DEFAULT_WAIT_FOR_CRD_STATUS_TIMEOUT) -> dict:
        """
        Status is a section in the CRD that is created after registration to
        assisted service and it defines the observed state of NMStateConfig.
        Since the status key is created only after resource is processed by the
        controller in the service, it might take a few seconds before appears.
        """

        def _attempt_to_get_status() -> dict:
            return self.get()["status"]

        return waiting.wait(
            _attempt_to_get_status,
            sleep_seconds=0.5,
            timeout_seconds=timeout,
            waiting_for=f"nmstate config {self.ref} status",
            expected_exceptions=KeyError,
        )
