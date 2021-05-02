import pytest

from tests.config import ClusterConfig
from test_infra.helper_classes.nodes import Nodes
from tests.base_test import BaseTest
from tests.conftest import get_available_openshift_versions

from junit_report import JunitTestSuite


class TestInstall(BaseTest):

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, nodes: Nodes, cluster, openshift_version):
        new_cluster = cluster(cluster_config=ClusterConfig(openshift_version=openshift_version))
        new_cluster.prepare_for_installation(nodes)
        new_cluster.start_install_and_wait_for_installed()
