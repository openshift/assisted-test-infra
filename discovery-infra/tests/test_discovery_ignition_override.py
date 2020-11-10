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
        new_cluster = cluster()
        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path = "/etc/test_discovery_ignition_override"
        ignition_override["storage"]["files"][0]["path"] = override_path
        new_cluster.patch_discovery_ignition(ignition=ignition_override)

        # Generate and download cluster ISO
        new_cluster.generate_and_download_image()
        # Boot nodes into ISO
        nodes.start_all()
        # Wait until hosts are discovered and update host roles
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.set_host_roles()
        # Verify override
        self._validate_ignition_override(nodes, TestDiscoveryIgnition.override_path)

    #  Test fails due to: "MGMT-2758 Invalidate existing discovery ISO in case the user
    #                                   created a discovery ignition override"
    @pytest.mark.regression
    def test_discovery_ignition_after_iso_was_created(self, api_client, nodes, cluster):
        """ Verify that we create a new ISO upon discovery igniton override in case one already exists.
        Download the ISO
        Create a discovery ignition override
        Download the ISO again
        Start the nodes
        Verify the override was applied
        """
        # Define new cluster
        new_cluster = cluster()

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path = "/etc/test_discovery_ignition_after_iso_was_created"
        ignition_override["storage"]["files"][0]["path"] = override_path

        # Generate and download cluster ISO
        new_cluster.generate_and_download_image()
        # Apply the patch after the ISO was created
        new_cluster.patch_discovery_ignition(ignition=ignition_override)
        # Generate and download cluster ISO again
        new_cluster.generate_and_download_image()

        # Boot nodes into ISO
        nodes.start_all()
        # Wait until hosts are discovered and update host roles
        new_cluster.wait_until_hosts_are_discovered()
        # Verify override
        self._validate_ignition_override(nodes, override_path)

    @pytest.mark.regression
    def test_discovery_ignition_bad_format(self, api_client, nodes, cluster):
        """Create a discovery ignition override with bad content
        make sure patch API fail
        """
        # Define new cluster
        new_cluster = cluster()

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        test_string = "not base 64b content"
        override_path = "/etc/test_discovery_ignition_bad_format"
        ignition_override["storage"]["files"][0]["path"] = override_path
        ignition_override["storage"]["files"][0]["contents"] = {"source": f"data:text/plain;base64,{test_string}"}
        try:
            new_cluster.patch_discovery_ignition(ignition=ignition_override)
        except Exception:
            logging.info("Got an exception while trying to update a cluster with unsupported discovery igniton")
        else:
            raise Exception("Expected patch_discovery_ignition to fail due to unsupported ignition version")

    @pytest.mark.regression
    def test_discovery_ignition_multiple_calls(self, api_client, nodes, cluster):
        """ Apply multiple discovery ignition overrides to the cluster.
        Create a discovery ignition override and than create another one
        Download the ISO
        Start the nodes
        Verify the last override was applied
        """
        # Define new cluster
        new_cluster = cluster()

        ignition_override = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path = "/etc/test_discovery_ignition_multiple_calls_1"
        ignition_override["storage"]["files"][0]["path"] = override_path
        new_cluster.patch_discovery_ignition(ignition=ignition_override)

        ignition_override_2 = copy.deepcopy(TestDiscoveryIgnition.base_ignition)
        override_path_2 = "/etc/test_discovery_ignition_multiple_calls_2"
        ignition_override_2["storage"]["files"][0]["path"] = override_path_2
        # Create another discovery ignition override
        new_cluster.patch_discovery_ignition(ignition=ignition_override_2)

        # Generate and download cluster ISO again
        new_cluster.generate_and_download_image()
        # Boot nodes into ISO
        nodes.start_all()
        # Wait until hosts are discovered and update host roles
        new_cluster.wait_until_hosts_are_discovered()

        # Verify override
        self._validate_ignition_override(nodes, override_path_2)

    @staticmethod
    def _validate_ignition_override(nodes, file_path, expected_content=TEST_STRING):
        logging.info("Verifying ignition override for all hosts")
        results = nodes.run_ssh_command_on_given_nodes(nodes.nodes, "cat {}".format(file_path))
        for _, result in results.items():
            assert result == expected_content
