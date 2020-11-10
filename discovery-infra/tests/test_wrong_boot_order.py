import pytest

from tests.base_test import BaseTest


class TestWrongBootOrder(BaseTest):
    @pytest.mark.regression
    def test_wrong_boot_order_one_node(self, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()

        # Change boot order of a random node
        node = nodes.get_random_node()
        node.set_boot_order(cd_first=True)

        # Start cluster install
        new_cluster.prepare_for_install(nodes)
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress()

        # Wait until wrong boot order
        new_cluster.wait_for_one_host_to_be_in_wrong_boot_order()

        # Reboot required nodes into ISO
        node.shutdown()
        node.set_boot_order(cd_first=False)
        node.start()

        # wait until all nodes are in Installed status, will fail in case one host in error
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()
