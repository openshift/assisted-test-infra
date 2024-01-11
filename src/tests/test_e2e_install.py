import pytest
import semver
from junit_report import JunitTestSuite

import consts
from tests.base_test import BaseTest
from tests.config import global_variables
from tests.conftest import get_available_openshift_versions, get_supported_operators


class TestInstall(BaseTest):
    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, cluster, openshift_version):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed(fall_on_pending_status=True)

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_infra_env_install(self, infra_env, openshift_version):
        infra_env.prepare_for_installation()

    @JunitTestSuite()
    @pytest.mark.parametrize("network_type", [consts.NetworkType.OpenShiftSDN, consts.NetworkType.OVNKubernetes])
    def test_networking(self, cluster, network_type):
        if semver.compare(global_variables.openshift_version, "4.15.0") >= 0:
            raise ValueError(
                "parametrization of network type not necessary from 4.15.0 and above,"
                " as the only supported network type is OVN"
            )
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed(fall_on_pending_status=True)

    @JunitTestSuite()
    @pytest.mark.parametrize("olm_operators", get_supported_operators())
    def test_olm_operator(self, cluster, olm_operators):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed(fall_on_pending_status=True)
