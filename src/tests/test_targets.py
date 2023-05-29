import json
from glob import glob
from pathlib import Path

import pytest
from assisted_service_client import PlatformType
from junit_report import JunitTestSuite

from assisted_test_infra.test_infra import ClusterName
from assisted_test_infra.test_infra.helper_classes.cluster import Cluster
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from consts import consts
from service_client import InventoryClient, SuppressAndLog, log
from tests.base_test import BaseTest
from tests.config import ClusterConfig, InfraEnvConfig


class TestMakefileTargets(BaseTest):
    @JunitTestSuite()
    def test_target_deploy_nodes(self, cluster):
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
    def test_destroy_terraform(
        self, api_client: InventoryClient, prepared_controller_configuration: BaseNodesConfig, cluster_configuration
    ):
        """Destroy cluster via terraform"""

        cluster_id = cluster_configuration.cluster_id
        clusters = api_client.clusters_list() if not cluster_id else [{"id": cluster_id}]

        for cluster_info in clusters:
            cluster = Cluster(api_client, ClusterConfig(cluster_id=cluster_info["id"]), InfraEnvConfig())
            controller = self.get_terraform_controller(prepared_controller_configuration, cluster._config)
            config_vars = controller.get_all_vars()
            controller.tf.set_vars(**config_vars)
            controller.tf.select_defined_variables()
            controller.destroy_all_nodes()

        log.info(f"Successfully destroyed {len(clusters)} clusters")

    @JunitTestSuite()
    def test_destroy_available_terraform(
        self, prepared_controller_configuration: BaseNodesConfig, cluster_configuration
    ):
        clusters_tf_folders = glob(f"{consts.TF_FOLDER}/*")
        destroyed_clusters = 0

        for cluster_dir in clusters_tf_folders:
            tfvar_files = glob(f"{cluster_dir}/*/{consts.TFVARS_JSON_NAME}", recursive=True)
            for tfvar_file in tfvar_files:
                with SuppressAndLog(Exception):
                    with open(tfvar_file) as f:
                        tfvars = json.load(f)

                    for key, value in tfvars.items():
                        if key == "cluster_name":
                            value = ClusterName(value)
                        if hasattr(cluster_configuration, key):
                            setattr(cluster_configuration, key, value)
                        if hasattr(prepared_controller_configuration, key):
                            setattr(prepared_controller_configuration, key, value)

                    platform = cluster_configuration.platform or PlatformType.BAREMETAL
                    if platform != Path(tfvar_file).resolve().parent.stem:
                        continue

                    controller = self.get_terraform_controller(prepared_controller_configuration, cluster_configuration)
                    config_vars = controller.get_all_vars()
                    controller.tf.set_vars(**config_vars)
                    controller.tf.select_defined_variables()
                    controller.destroy_all_nodes()
                    destroyed_clusters += 1

        log.info(f"Successfully destroyed {destroyed_clusters} clusters")
