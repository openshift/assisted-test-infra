import pytest
from junit_report import JunitTestSuite

from assisted_test_infra.test_infra.helper_classes.config import BaseNodeConfig
from tests.base_test import BaseTest


class TestMakefileTargets(BaseTest):
    @JunitTestSuite()
    def test_target_deploy_nodes(self, cluster):
        cluster.prepare_for_installation()

    @JunitTestSuite()
    def test_target_install_with_deploy_nodes(self, prepared_cluster):
        prepared_cluster.start_install_and_wait_for_installed()

    @pytest.fixture
    def download_iso_override_nodes_count(self, prepared_controller_configuration: BaseNodeConfig):
        """No need creating any nodes for creating a cluster and download its ISO
        Setting masters_count and workers_count to 0 on with overriding controller_configuration fixture return value
        before nodes creation causing Nodes object not to generate any new nodes"""

        prepared_controller_configuration.masters_count = 0
        prepared_controller_configuration.workers_count = 0
        yield prepared_controller_configuration

    @JunitTestSuite()
    @pytest.mark.override_controller_configuration(download_iso_override_nodes_count.__name__)
    def test_target_download_iso(self, cluster):
        cluster.download_image()
