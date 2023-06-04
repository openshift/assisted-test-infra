import datetime
import os

import kubernetes.client
import kubernetes.config
import kubernetes.dynamic
import pytest
from junit_report import JunitTestSuite

from service_client import log
from tests.base_test import BaseTest


class TestUpgradeAgent(BaseTest):
    @pytest.fixture(scope="session")
    def namespace(self) -> str:
        return os.environ.get("NAMESPACE", "assisted-isntaller")

    @pytest.fixture(scope="session")
    def k8s_client(self) -> kubernetes.dynamic.DynamicClient:
        return kubernetes.dynamic.DynamicClient(
            kubernetes.client.api_client.ApiClient(
                configuration=kubernetes.config.load_kube_config(),
            ),
        )

    @classmethod
    def _get_other_agent_image(cls) -> str:
        """Returns the reference to the other agent image."""
        return os.environ.get("OTHER_AGENT_IMAGE", "quay.io/edge-infrastructure/assisted-installer-agent:v2.20.1")

    @classmethod
    def _get_current_agent_image(
        cls,
        client: kubernetes.dynamic.DynamicClient,
        namespace: str,
    ) -> str:
        """Returns the agent image the is currently used by the service."""
        configmaps_api = client.resources.get(api_version="v1", kind="ConfigMap")
        configmap = configmaps_api.get(namespace=namespace, name="assisted-service-config")
        return configmap.data["AGENT_DOCKER_IMAGE"]

    @classmethod
    def _load_service_with_agent_image(
        cls,
        client: kubernetes.dynamic.DynamicClient,
        namespace: str,
        image: str,
    ) -> None:
        """
        Checks if the service is already using the given agent image. If it isn't using it then it changes the configmap
        to use it and restarts the deployment.
        """
        # Check if the service is already using the given agent image:
        current = cls._get_current_agent_image(client, namespace)
        if current == image:
            log.info(f"Service is already using agent image '{image}'")
            return

        # Update the configuration:
        configmaps_api = client.resources.get(api_version="v1", kind="ConfigMap")
        configmaps_api.patch(
            namespace=namespace,
            name="assisted-service-config",
            body={
                "data": {
                    "AGENT_DOCKER_IMAGE": image,
                },
            },
        )
        log.info(f"Updated configuration with agent image '{image}'")

        # Restart the deployment:
        deployments_api = client.resources.get(api_version="apps/v1", kind="Deployment")
        date = datetime.datetime.now(datetime.timezone.utc).isoformat()
        deployments_api.patch(
            namespace=namespace,
            name="assisted-service",
            body={
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": date,
                            },
                        },
                    },
                },
            },
        )
        log.info(f"Restarted deployment with agent image '{image}'")

    @JunitTestSuite()
    def test_upgrade_agent(self, cluster, namespace, k8s_client):
        """
        This test prepares the cluster with an image different to the current one. Once it is ready to install it
        restarts the current image and wait till all the hosts have been upgraded to use it.
        """
        assert (current_image := self._get_current_agent_image(k8s_client, namespace))
        assert (other_image := self._get_other_agent_image())
        log.info(f"Other agent image is '{other_image}'")
        log.info(f"Current agent image is '{current_image}'")

        try:
            # Prepare the cluster for installation using the other image:
            log.info("Waiting for cluster to be ready to install with agent image '%s'", other_image)
            self._load_service_with_agent_image(k8s_client, namespace, other_image)
            cluster.prepare_for_installation()

            # Restart the service with the current agent image and wait till all host are using it:
            log.info("Waiting for hosts to use agent image '%s'", current_image)
            self._load_service_with_agent_image(k8s_client, namespace, current_image)
            cluster.wait_until_hosts_use_agent_image(current_image)
        finally:
            self._load_service_with_agent_image(k8s_client, namespace, current_image)
