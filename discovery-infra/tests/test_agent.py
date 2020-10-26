import logging
import pytest
import waiting
from tests.base_test import BaseTest


class TestAgent(BaseTest):

    @pytest.mark.regression
    def test_kill_agent(self, api_client, node_controller, cluster):
        # start vms, kill agent, validate it was restarted and works

        # Define new cluster
        cluster_id = cluster().id
        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Boot nodes into ISO
        hosts = node_controller.start_all_nodes()
        test_host = list(hosts.values())[0]
        waiting.wait(
            lambda: test_host.is_service_active("agent") is True,
            timeout_seconds=60,
            sleep_seconds=5,
            waiting_for="Waiting for agent",
        )
        # kill agent
        test_host.kill_service("agent")
        # wait till agent is up
        waiting.wait(
            lambda: test_host.is_service_active("agent") is True,
            timeout_seconds=60,
            sleep_seconds=5,
            waiting_for="Waiting for agent",
        )
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
