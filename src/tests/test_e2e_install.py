from contextlib import suppress

import pytest
from _pytest.fixtures import FixtureLookupError, FixtureRequest
from junit_report import JunitTestSuite

import consts
from assisted_test_infra.test_infra.helper_classes.config import BaseNodeConfig, VSphereControllerConfig
from tests.base_test import BaseTest
from tests.config import ClusterConfig, TerraformConfig
from tests.conftest import get_available_openshift_versions, global_variables
from tests.global_variables import get_default_triggers


class TestInstall(BaseTest):
    @pytest.fixture
    def new_controller_configuration(self, request) -> BaseNodeConfig:
        """
        Creates the controller configuration object according to the platform.
        Override this fixture in your test class to provide a custom configuration object
        :rtype: new node controller configuration
        """
        if global_variables.platform == consts.Platforms.VSPHERE:
            config = VSphereControllerConfig()
        else:
            config = TerraformConfig()

        with suppress(FixtureLookupError):
            operators = request.getfixturevalue("olm_operators")
            self.update_olm_configuration(config, operators)

        return config

    @pytest.fixture
    def new_cluster_configuration(self, request: FixtureRequest):
        # Overriding the default BaseTest.new_cluster_configuration fixture to set custom configs.
        config = ClusterConfig()

        for fixture_name in ["openshift_version", "network_type", "is_static_ip", "olm_operators"]:
            with suppress(FixtureLookupError):
                if hasattr(config, fixture_name):
                    config.set_value(fixture_name, request.getfixturevalue(fixture_name))
                else:
                    raise AttributeError(f"No attribute name {fixture_name} in ClusterConfig object type")
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
    @pytest.mark.parametrize("olm_operators", sorted(global_variables.get_api_client().get_supported_operators()))
    def test_olm_operator(self, cluster, olm_operators):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed()
