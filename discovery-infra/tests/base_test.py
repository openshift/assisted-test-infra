import logging
import pytest
import json
import os
import tarfile
import shutil
import time
from contextlib import suppress
from typing import Optional

from test_infra import consts
import test_infra.utils as infra_utils
from test_infra.tools.assets import NetworkAssets
from assisted_service_client.rest import ApiException
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.nodes import Nodes
from tests.conftest import env_variables, qe_env
from download_logs import download_logs


class BaseTest:

    @pytest.fixture(scope="function")
    def nodes(self, setup_node_controller):
        net_asset = None
        try:
            if not qe_env:
                net_asset = NetworkAssets()
                env_variables["net_asset"] = net_asset.get()
            controller = setup_node_controller(**env_variables)
            nodes = Nodes(controller, env_variables["private_ssh_key_path"])
            nodes.prepare_nodes()
            yield nodes
            logging.info(f'--- TEARDOWN --- node controller\n')
            nodes.destroy_all_nodes()
        finally:
            if not qe_env:
                net_asset.release_all()

    @pytest.fixture()
    def cluster(self, api_client, request):
        clusters = []

        def get_cluster_func(cluster_name: Optional[str] = None,
                             additional_ntp_source: Optional[str] = consts.DEFAULT_ADDITIONAL_NTP_SOURCE):
            if not cluster_name:
                cluster_name = infra_utils.get_random_name(length=10)

            res = Cluster(api_client=api_client,
                          cluster_name=cluster_name,
                          additional_ntp_source=additional_ntp_source)
            clusters.append(res)
            return res

        yield get_cluster_func

        for cluster in clusters:
            logging.info(f'--- TEARDOWN --- Collecting Logs for test: {request.node.name}\n')
            self.collect_test_logs(cluster, api_client, request.node)
            logging.info(f'--- TEARDOWN --- deleting created cluster {cluster.id}\n')
            if cluster.is_installing() or cluster.is_finalizing():
                cluster.cancel_install()

            with suppress(ApiException):
                cluster.delete()

    @pytest.fixture()
    def iptables(self):
        rules = []

        def set_iptables_rules_for_nodes(
            cluster, 
            nodes,
            given_nodes,
            iptables_rules,  
            download_image=True,
            iso_download_path=env_variables['iso_download_path'],
            ssh_key=env_variables['ssh_public_key']
            ):
            given_node_ips=[]
            if download_image:
                cluster.generate_and_download_image(
                    iso_download_path=iso_download_path,
                    ssh_key=ssh_key
                )
                nodes.start_given(given_nodes)
                for node in given_nodes:
                    given_node_ips.append(node.ips[0])
                nodes.shutdown_given(given_nodes)
            else:
                for node in given_nodes:
                    given_node_ips.append(node.ips[0])

            logging.info(f'Given node ips: {given_node_ips}')

            for rule in iptables_rules:
                rule.add_sources(given_node_ips)
                rules.append(rule)
                rule.insert()

        yield set_iptables_rules_for_nodes
        logging.info('---TEARDOWN iptables ---')
        for rule in rules:
            rule.delete()

    @staticmethod
    def get_cluster_by_name(api_client, cluster_name):
        clusters = api_client.clusters_list()
        for cluster in clusters:
            if cluster['name'] == cluster_name:
                return cluster
        return None

    @staticmethod
    def assert_http_error_code(api_call, status, reason, **kwargs):
        with pytest.raises(ApiException) as response:
            api_call(**kwargs)
        assert response.value.status == status
        assert response.value.reason == reason

    @staticmethod
    def assert_cluster_validation(cluster_info, validation_section, validation_id, expected_status):
        found_status = infra_utils.get_cluster_validation_value(cluster_info, validation_section, validation_id)
        assert found_status == expected_status, "Found validation status " + found_status + " rather than " +\
                                                expected_status + " for validation " + validation_id

    @staticmethod
    def assert_string_length(string, expected_len):
        assert len(string) == expected_len, "Expected len string of: " + str(expected_len) + \
                                            " rather than: " + str(len(string)) + " String value: " + string

    @staticmethod
    def collect_test_logs(cluster, api_client, test):
        log_dir_name = f"{env_variables['log_folder']}/{test.name}"
        with suppress(ApiException):
            cluster_details = json.loads(json.dumps(cluster.get_details().to_dict(), sort_keys=True, default=str))
            download_logs(api_client, cluster_details, log_dir_name, test.result_call.failed)

    @staticmethod
    def verify_no_logs_uploaded(cluster, cluster_tar_path):
        with pytest.raises(ApiException) as ex:
            cluster.download_installation_logs(cluster_tar_path)
        assert "No log files" in str(ex.value)
