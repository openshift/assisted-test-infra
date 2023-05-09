from glob import glob
from pathlib import Path

import pytest
from junit_report import JunitTestSuite

import consts
from assisted_test_infra.test_infra.helper_classes.cluster import Cluster
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from assisted_test_infra.test_infra.tools import TerraformUtils
from service_client import InventoryClient, SuppressAndLog, log
from tests.base_test import BaseTest
from tests.config import ClusterConfig, InfraEnvConfig


class TestMakefileTargets(BaseTest):
    @JunitTestSuite()
    def test_target_deploy_nodes(self, cluster):
        cluster.prepare_nodes()

    @JunitTestSuite()
    def test_target_deploy_networking_with_nodes(self, cluster):
        cluster.prepare_for_installation()

    @JunitTestSuite()
    def test_target_install_with_deploy_nodes(self, prepared_cluster):
        prepared_cluster.start_install_and_wait_for_installed()

    @pytest.fixture
    def download_iso_override_nodes_count(self, prepared_controller_configuration: BaseNodesConfig):
        """No need creating any nodes for creating a cluster and download its ISO
        Setting masters_count and workers_count to 0 on with overriding controller_configuration fixture return value
        before nodes creation causing Nodes object not to generate any new nodes"""

        prepared_controller_configuration.masters_count = 0
        prepared_controller_configuration.workers_count = 0
        yield prepared_controller_configuration

    @pytest.mark.override_controller_configuration(download_iso_override_nodes_count.__name__)
    def test_target_download_iso(self, cluster):
        cluster.download_image()

    @JunitTestSuite()
    def test_delete_clusters(self, api_client: InventoryClient, cluster_configuration):
        """Delete all clusters or single cluster if CLUSTER_ID is given"""

        cluster_id = cluster_configuration.cluster_id
        clusters = api_client.clusters_list() if not cluster_id else [{"id": cluster_id}]

        for cluster_info in clusters:
            cluster = Cluster(api_client, ClusterConfig(cluster_id=cluster_info["id"]), InfraEnvConfig())
            cluster.delete()

        log.info(f"Successfully deleted {len(clusters)} clusters")

    @JunitTestSuite()
    def test_destroy_terraform(self):
        clusters_dirs = glob(f"{consts.TF_FOLDER}/*")
        for cluster_dir in clusters_dirs:
            tfvar_files = glob(f"{cluster_dir}/*/{consts.TFVARS_JSON_NAME}", recursive=True)
            for tfvar_file in tfvar_files:
                with SuppressAndLog(Exception):
                    tf_folder = Path(tfvar_file).resolve().parent
                    tf = TerraformUtils(str(tf_folder))
                    tf.destroy(force=False)
