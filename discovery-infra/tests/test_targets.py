from junit_report import JunitTestSuite

from tests.base_test import BaseTest


class TestMakefileTargets(BaseTest):

    @JunitTestSuite()
    def test_deploy_nodes(self, cluster):
        cluster.prepare_for_installation()

    @JunitTestSuite()
    def test_install_with_deploy_nodes(self, prepared_cluster):
        prepared_cluster.start_install_and_wait_for_installed()
