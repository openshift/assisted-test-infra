import pytest

from tests.base_test import BaseTest


class TestWrongBootOrder(BaseTest):
    @pytest.mark.regression
    def test_wrong_boot_order_one_node(self, api_client, node_controller, cluster):
        # Define new cluster
        cluster_id = cluster().id
        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Change boot order of a random node
        hosts = node_controller.list_nodes()
        node = list(hosts.values())[0]
        node.set_boot_order(cd_first=True)
        # Boot nodes into ISO
        node_controller.start_all_nodes()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(cluster_id=cluster_id,
                                api_client=api_client,
                                controller=node_controller
                                )
        # Start cluster install
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_installing_in_progress(cluster_id=cluster_id, api_client=api_client)
        # Wait until wrong boot order
        self.wait_for_one_host_to_be_in_wrong_boot_order(cluster_id=cluster_id,
                                                         api_client=api_client)
        # Reboot required nodes into ISO
        node.shutdown()
        node.set_boot_order(cd_first=False)
        node.start()
        # Wait for host to keep installing
        self.wait_for_nodes_status_installing_or_installed(cluster_id=cluster_id,
                                                           api_client=api_client)
        # wait until all nodes are in Installed status, will fail in case one host in error
        self.wait_for_nodes_to_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)
