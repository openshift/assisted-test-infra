import pytest

from tests.base_test import BaseTest


class TestFormatBootableDisks(BaseTest):
    @pytest.mark.regression
    def test_format_bootable_disk_one_node(self, api_client, node_controller, cluster):
        # Define new cluster
        cluster_id = cluster().id
        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Add additional disk to a random node
        hosts = node_controller.list_nodes()
        node = hosts[0]
        node.add_disk(size="1")
        node_controller.start_all_nodes()
        # node.make_fs()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        # Check inventory for bootable disks
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(cluster_id=cluster_id,
                                api_client=api_client,
                                controller=node_controller
                                )
        # Start cluster install
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_installing_in_progress(cluster_id=cluster_id, api_client=api_client)
        # Check inventory

