import logging
import pytest
import waiting
from tests.base_test import BaseTest


class TestAgent(BaseTest):

    @pytest.mark.regression
    def test_kill_agent(self, nodes, cluster):
        # start vms, kill agent, validate it was restarted and works

        # Define new cluster
        new_cluster = cluster()
        # Generate and download cluster ISO
        new_cluster.generate_and_download_image()
        # Boot nodes into ISO
        nodes.start_all()
        test_node = nodes.get_random_node()
        waiting.wait(
            lambda: test_node.is_service_active("agent") is True,
            timeout_seconds=60 * 6,
            sleep_seconds=5,
            waiting_for="Waiting for agent",
        )
        # kill agent
        test_node.kill_service("agent")
        # wait till agent is up
        waiting.wait(
            lambda: test_node.is_service_active("agent") is True,
            timeout_seconds=60 * 6,
            sleep_seconds=5,
            waiting_for="Waiting for agent",
        )
        # Wait until hosts are discovered and update host roles
        new_cluster.wait_until_hosts_are_discovered()
