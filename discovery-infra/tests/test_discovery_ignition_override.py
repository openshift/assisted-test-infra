import pytest
import base64
from tests.base_test import BaseTest


class TestDiscoveryIgnition(BaseTest):

    @pytest.mark.regression
    def test_discovery_ignition_override(self, api_client, node_controller, cluster):
        # Create a discovery ignition override
        # Start the nodes
        # Verify the override was applied
        override_path = "/ignition/file_override"
        test_string = "I can write tests all day long"
        ignition_override = {"ignition": {"version": "3.1.0"}, "storage": {"files": [
            {"path": override_path,
             "contents": {"source": "data:text/plain;base64,{}".format(base64.b64encode(test_string))}}]}}

        # Define new cluster
        cluster_id = cluster().id
        api_client.patch_cluster_discovery_ignition(cluster_id, ignition_override)
        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Boot nodes into ISO
        hosts = node_controller.start_all_nodes()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        # Verify override
        for test_host in hosts:
            file_content = test_host.run_command("cat {}".format(override_path))
            assert file_content == test_string

    @pytest.mark.regression
    def test_discovery_ignition_bad_version(self, api_client, node_controller, cluster):
        # Create a discovery ignition override with old revision (2.2.0)
        # make sure patch API fail
        pass
