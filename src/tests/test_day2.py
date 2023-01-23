from junit_report import JunitTestSuite

from tests.base_test import BaseTest


class TestDay2(BaseTest):

    # Install day1 cluster and deploy day2 nodes (cloud flow).
    # Or, deploy day2 nodes on an installed cluster if CLUSTER_ID env var is specified.
    @JunitTestSuite()
    def test_deploy_day2_nodes_cloud(self, day2_cluster):
        day2_cluster.prepare_for_installation()
        day2_cluster.start_install_and_wait_for_installed()
