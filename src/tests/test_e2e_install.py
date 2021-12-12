from contextlib import suppress

import pytest
from _pytest.fixtures import FixtureLookupError, FixtureRequest
from junit_report import JunitTestSuite

from assisted_test_infra.test_infra import consts
from tests.base_test import BaseTest
from tests.config import ClusterConfig
from tests.conftest import get_available_openshift_versions, global_variables
from tests.global_variables import get_default_triggers


class TestInstall(BaseTest):
    @pytest.fixture
    def new_cluster_configuration(self, request: FixtureRequest):
        # Overriding the default BaseTest.new_cluster_configuration fixture to set custom configs.
        config = ClusterConfig()

        for fixture_name in ["openshift_version", "network_type", "is_static_ip"]:
            with suppress(FixtureLookupError):
                setattr(config, fixture_name, request.getfixturevalue(fixture_name))

        config.trigger(get_default_triggers())
        return config

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, cluster, openshift_version):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed()

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_infra_env_install(self, infra_env, openshift_version):
        infra_env.prepare_for_installation()

    @JunitTestSuite()
    @pytest.mark.parametrize("is_static_ip", [False, True])
    @pytest.mark.parametrize("network_type", [consts.NetworkType.OpenShiftSDN, consts.NetworkType.OVNKubernetes])
    def test_networking(self, cluster, network_type, is_static_ip):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed()

    @JunitTestSuite()
    @pytest.mark.parametrize("operators", sorted(global_variables.get_api_client().get_supported_operators()))
    def test_olm_operator(self, configs, get_nodes, get_cluster, operators, update_olm_config):
        cluster_config, tf_config = configs
        update_olm_config(tf_config=tf_config, cluster_config=cluster_config, operators=operators)

        new_cluster = get_cluster(get_nodes(tf_config, cluster_config), cluster_config)
        new_cluster.prepare_for_installation()
        new_cluster.start_install_and_wait_for_installed()
        assert new_cluster.is_operator_in_status(operators, consts.OperatorStatus.AVAILABLE)
