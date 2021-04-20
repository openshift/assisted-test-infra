import pytest
from tests.base_test import BaseTest
from tests.conftest import get_available_openshift_versions

from junit_report import JunitTestSuite


class TestInstall(BaseTest):

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, nodes, cluster, openshift_version):
        new_cluster = cluster(openshift_version=openshift_version)
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install_and_wait_for_installed()
