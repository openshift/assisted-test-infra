import time
from typing import Tuple

import pytest
from junit_report import JunitTestSuite
from test_infra.consts import OperatorStatus

from tests.base_test import BaseTest
from tests.config import ClusterConfig, TerraformConfig
from tests.conftest import get_available_openshift_versions, get_api_client


class TestInstall(BaseTest):

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, configs: Tuple[ClusterConfig, TerraformConfig], get_nodes, get_cluster, openshift_version):
        cluster_config, tf_config = configs
        cluster_config.openshift_version = openshift_version
        new_cluster = get_cluster(get_nodes(tf_config, cluster_config), cluster_config)
        new_cluster.prepare_for_installation()
        new_cluster.start_install_and_wait_for_installed()

    @JunitTestSuite()
    @pytest.mark.parametrize("sleep_time", [1, 60])
    def test_dummy(self, configs: Tuple[ClusterConfig, TerraformConfig], get_nodes, get_cluster, sleep_time):
        cluster_config, tf_config = configs
        new_cluster = get_cluster(get_nodes(tf_config, cluster_config), cluster_config)
        new_cluster.prepare_for_installation()
        time.sleep(sleep_time)

    @JunitTestSuite()
    @pytest.mark.parametrize("operators", sorted(get_api_client().get_supported_operators()))
    def test_olm_operator(self, configs, get_nodes, get_cluster, operators, update_olm_config):
        cluster_config, tf_config = configs
        update_olm_config(tf_config=tf_config, cluster_config=cluster_config, operators=operators)

        new_cluster = get_cluster(get_nodes(tf_config, cluster_config), cluster_config)
        new_cluster.prepare_for_installation()
        new_cluster.start_install_and_wait_for_installed()
        assert new_cluster.is_operator_in_status(operators, OperatorStatus.AVAILABLE)
