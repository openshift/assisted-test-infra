from junit_report import JunitTestSuite

from tests.base_test import BaseTest
from tests.config import global_variables


class TestDay2(BaseTest):

    # Install day1 cluster and deploy day2 nodes (cloud flow).
    # Or, deploy day2 nodes on an installed cluster if CLUSTER_ID env var is specified.
    @JunitTestSuite()
    def test_deploy_day2_nodes_cloud(self, cluster, day2_cluster, controller):
        if not global_variables.cluster_id:
            cluster.nodes.destroy_all_nodes()
            cluster.nodes.prepare_nodes()
            cluster.prepare_for_installation()
            cluster.start_install_and_wait_for_installed()

        day2_cluster.config.day1_cluster_id = cluster.id
        day2_cluster.prepare_for_installation(iso_download_path=cluster.get_iso_download_path())
        day2_cluster.start_install_and_wait_for_installed(controller)
