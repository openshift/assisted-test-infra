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
    def _get_previous_agent_image(cls) -> str:
        """Returns the reference to the previous agent image."""
        return os.environ.get("PREVIOUS_AGENT_IMAGE", "quay.io/edge-infrastructure/assisted-installer-agent:v2.9.0")

    @classmethod
    def _get_broken_agent_image(cls) -> str:
        """Returns an agent image reference that doesn't exist."""
        return os.environ.get("BROKEN_AGENT_IMAGE", "quay.io/edge-infrastructure/assisted-installer-agent:broken")

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
        This test will prepare the cluster with the previous agent image. Once it is ready to install it will restart
        the service with an agent image that doesn't exist, so that all the hosts will move to `insufficient`. Then it
        will restart the service again with the current image, so that host will upgrade and move to `ready` again.
        """
        assert (current_image := self._get_current_agent_image(k8s_client, namespace))
        assert (previous_image := self._get_previous_agent_image())
        assert (broken_image := self._get_broken_agent_image())
        log.info(f"Previous image is '{previous_image}'")
        log.info(f"Broken image is '{broken_image}'")
        log.info(f"Current image is '{current_image}'")

        try:
            # Prepare the cluster for installation using the previous image:
            log.info("Waiting for cluster to move to 'ready' with previous image")
            self._load_service_with_agent_image(k8s_client, namespace, previous_image)
            cluster.prepare_for_installation()

            # Restart the service with the broken agent image, so that nodes will not be able to pull it and move to the
            # insufficient state:
            log.info("Waiting for hosts to move to 'insufficient' with broken image")
            self._load_service_with_agent_image(k8s_client, namespace, broken_image)
            cluster.wait_until_hosts_are_insufficient()

            # Restart the agent with the current agent image and wait for all hosts to be ready, which means that they
            # upgraded correctly:
            log.info("Waiting for hosts to move to 'ready'")
            self._load_service_with_agent_image(k8s_client, namespace, current_image)
            cluster.wait_for_ready_to_install()
        finally:
            self._load_service_with_agent_image(k8s_client, namespace, current_image)
