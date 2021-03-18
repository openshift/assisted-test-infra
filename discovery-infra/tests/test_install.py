from pathlib import Path

import pytest
from tests.base_test import BaseTest
from tests.conftest import get_api_client

from test_infra.junit_report import JunitTestCase, JunitTestSuite


class TestInstall(BaseTest):

    @JunitTestSuite(Path().cwd().joinpath("reports"))
    @pytest.mark.parametrize("openshift_version", list(get_api_client().get_openshift_versions().keys()))
    def test_install(self, nodes, cluster, openshift_version):
        # Define new cluster
        new_cluster = self.get_cluster(cluster, openshift_version)
        self.prepare_for_install(new_cluster, nodes)
        # Install Cluster
        self.start_install_and_wait_for_installed(new_cluster)

    @JunitTestCase()
    def get_cluster(self, cluster, openshift_version):
        return cluster(openshift_version=openshift_version)

    @JunitTestCase()
    def prepare_for_install(self, new_cluster, nodes):
        new_cluster.prepare_for_install(nodes=nodes)

    @JunitTestCase()
    def start_install_and_wait_for_installed(self, new_cluster):
        new_cluster.start_install_and_wait_for_installed()
