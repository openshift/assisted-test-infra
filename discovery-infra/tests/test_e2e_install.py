import pytest

from tests.config import ClusterConfig
from test_infra.helper_classes.nodes import Nodes
from tests.base_test import BaseTest
from tests.conftest import get_available_openshift_versions, get_api_client

from junit_report import JunitTestSuite


class TestInstall(BaseTest):

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, nodes: Nodes, cluster, openshift_version):
        new_cluster = cluster(cluster_config=ClusterConfig(openshift_version=openshift_version))
        new_cluster.prepare_for_installation(nodes)
        new_cluster.start_install_and_wait_for_installed()

    @JunitTestSuite()
    # TODO: Fix OCS
    # @pytest.mark.parametrize("olm_operator", get_api_client().get_supported_operators())
    @pytest.mark.parametrize("olm_operator", ["lso", "cnv"])
    def test_olm_operator(self, nodes: Nodes, cluster, olm_operator):
        new_cluster = cluster(cluster_config=ClusterConfig(olm_operators=[olm_operator]))
        new_cluster.prepare_for_installation(nodes, olm_operators=[olm_operator])
        new_cluster.start_install_and_wait_for_installed()
