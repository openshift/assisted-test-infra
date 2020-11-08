import logging
import copy
import pytest
import base64
from tests.base_test import BaseTest

TEST_STRING = "I can write tests all day long"


class TestDiscoveryIgnition(BaseTest):
    base64_encoded_test_string = base64.b64encode(TEST_STRING.encode("utf-8")).decode("utf-8")
    override_path = "/etc/test_discovery_ignition_override"
    base_ignition = {
        "ignition": {
            "version": "3.1.0"
        },
        "storage": {
            "files": [
                {
                    "path": override_path,
                    "contents": {"source": f"data:text/plain;base64,{base64_encoded_test_string}"}
                }
            ]
        }
    }

    @pytest.mark.regression
    def test_discovery_ignition_override(self, api_client, nodes, cluster):
        """ Test happy flow.

        Create a discovery ignition override
        Start the nodes
        Verify the override was applied
        """
        # Define new cluster
        cluster_id = cluster().id

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path = "/etc/test_discovery_ignition_override"
        ignition_override["storage"]["files"][0]["path"] = override_path
        api_client.patch_cluster_discovery_ignition(cluster_id, ignition_override)

        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Boot nodes into ISO
        nodes.start_all()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        # Verify override
        self.validate_ignition_override(nodes, TestDiscoveryIgnition.override_path)

    # TODO: replace "skip" with "regression" once:
    #  "MGMT-2758 Invalidate existing discovery ISO in case the user created a discovery ignition override" is done
    @pytest.mark.skip
    def test_discovery_ignition_after_ISO_was_created(self, api_client, node_controller, cluster):
        """ Verify that we create a new ISO upon discovery igniton override in case one already exists.
        Download the ISO
        Create a discovery ignition override
        Download the ISO again
        Start the nodes
        Verify the override was applied
        """
        # Define new cluster
        cluster_id = cluster().id

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path = "/etc/test_discovery_ignition_after_ISO_was_created"
        ignition_override["storage"]["files"][0]["path"] = override_path

        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Apply the patch after the ISO was created
        api_client.patch_cluster_discovery_ignition(cluster_id, ignition_override)
        # Generate and download cluster ISO again
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)

        # Boot nodes into ISO
        hosts = node_controller.start_all_nodes()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        # Verify override
        self.validate_ignition_override(hosts, override_path)

    @pytest.mark.regression
    def test_discovery_ignition_bad_format(self, api_client, node_controller, cluster):
        """Create a discovery ignition override with bad content
        make sure patch API fail
        """
        # Define new cluster
        cluster_id = cluster().id

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        test_string = "not base 64b content"
        override_path = "/etc/test_discovery_ignition_bad_format"
        ignition_override["storage"]["files"][0]["path"] = override_path
        ignition_override["storage"]["files"][0]["contents"] = {"source": f"data:text/plain;base64,{test_string}"}

        try:
            api_client.patch_cluster_discovery_ignition(cluster_id, ignition_override)
        # TODO: change this to BadRequest
        except Exception:
            logging.info("Got an exception while trying to update a cluster with unsupported discovery igniton")
        else:
            raise Exception("Expected patch_cluster_discovery_ignition to fail due to unsupported ignition version")

    @pytest.mark.regression
    def test_discovery_ignition_multiple_calls(self, api_client, nodes, cluster):
        """ Apply multiple discovery ignition overrides to the cluster.
        Create a discovery ignition override and than create another one
        Download the ISO
        Start the nodes
        Verify the last override was applied
        """
        # Define new cluster
        cluster_id = cluster().id

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path = "/etc/test_discovery_ignition_multiple_calls_1"
        ignition_override["storage"]["files"][0]["path"] = override_path
        api_client.patch_cluster_discovery_ignition(cluster_id, ignition_override)

        ignition_override_2 = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path_2 = "/etc/test_discovery_ignition_multiple_calls_2"
        ignition_override_2["storage"]["files"][0]["path"] = override_path_2
        # Create another discovery ignition override
        api_client.patch_cluster_discovery_ignition(cluster_id, ignition_override_2)

        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Boot nodes into ISO
        nodes.start_all()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        # Verify override
        self.validate_ignition_override(nodes, override_path_2)

    @staticmethod
    def validate_ignition_override(nodes, file_path, expected_content=TEST_STRING):
        logging.info("Verifying pplied the override for all hosts")
        results = nodes.run_ssh_command_on_given_nodes(nodes.nodes, "cat {}".format(file_path))
        for _, result in results.items():
            assert result == expected_content
