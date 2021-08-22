import time
from contextlib import suppress

import pytest
from _pytest.fixtures import FixtureLookupError
from junit_report import JunitTestSuite

from test_infra.consts import OperatorStatus

from tests.base_test import BaseTest
from tests.config import ClusterConfig
from tests.conftest import get_available_openshift_versions, global_variables


class TestInstall(BaseTest):

    @pytest.fixture
    def new_cluster_configuration(self, request):
        # Overriding the default BaseTest.new_cluster_configuration fixture to set the openshift version.
        config = ClusterConfig()

        with suppress(FixtureLookupError):
            # Resolving the param value.
            version = request.getfixturevalue("openshift_version")
            config.openshift_version = version

        return config

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, cluster, openshift_version):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed()

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_infra_env_install(self, infra_env, openshift_version):
        infra_env.prepare_infraenv()

    @JunitTestSuite()
    @pytest.mark.parametrize("operators", sorted(global_variables.get_api_client().get_supported_operators()))
    def test_olm_operator(self, configs, get_nodes, get_cluster, operators, update_olm_config):
        cluster_config, tf_config = configs
        update_olm_config(tf_config=tf_config, cluster_config=cluster_config, operators=operators)

        new_cluster = get_cluster(get_nodes(tf_config, cluster_config), cluster_config)
        new_cluster.prepare_for_installation()
        new_cluster.start_install_and_wait_for_installed()
        assert new_cluster.is_operator_in_status(operators, OperatorStatus.AVAILABLE)
