import pytest

from tests.base_test import BaseTest

class TestInstall(BaseTest):
    def test_install(self, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        # Install Cluster
        new_cluster.start_install_and_wait_for_installed()