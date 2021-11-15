import day2
import pytest
from junit_report import JunitTestSuite
from tests.base_test import BaseTest
from tests.config import ClusterConfig, global_variables
from types import SimpleNamespace


class TestDay2(BaseTest):
    @pytest.fixture
    def new_cluster_configuration(self):
        return self.override_cluster_configuration()

    def override_cluster_configuration(self):
        config = ClusterConfig()
        config.cluster_id = global_variables.cluster_id
        return config

    # Install day1 cluster and deploy day2 nodes (cloud flow).
    # Or, deploy day2 nodes on an installed cluster if CLUSTER_ID env var is specified.
    @JunitTestSuite()
    def test_deploy_day2_nodes_cloud(self, cluster, new_cluster_configuration: ClusterConfig):
        if not global_variables.cluster_id:
            cluster.prepare_for_installation()
            cluster.start_install_and_wait_for_installed()

        # TODO: Use a proper structure instead of mimicking cli options
        args = SimpleNamespace()
        args.api_client = cluster.api_client
        args.pull_secret = new_cluster_configuration.pull_secret
        args.with_static_network_config = new_cluster_configuration.is_static_ip
        args.num_day2_workers = global_variables.num_day2_workers
        args.ssh_key = global_variables.ssh_public_key
        args.install_cluster = True

        if new_cluster_configuration.proxy:
            args.http_proxy = new_cluster_configuration.proxy.http_proxy
            args.https_proxy = new_cluster_configuration.proxy.https_proxy
            args.no_proxy = new_cluster_configuration.proxy.no_proxy

        day2.execute_day2_cloud_flow(new_cluster_configuration.cluster_id, args, new_cluster_configuration.is_ipv6)
