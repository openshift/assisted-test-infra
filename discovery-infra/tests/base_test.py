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

    @staticmethod
    def verify_logs_uploaded(cluster_tar_path, expected_min_log_num, installation_success):

        # verify that logs were collected from all expected sources
        assert (os.path.exists(cluster_tar_path))
        dir_path = cluster_tar_path.split(".")[0]
        try:
            with tarfile.open(cluster_tar_path) as tar:
                logging.info(f'downloaded logs: {tar.getnames()}')
                assert len(tar.getnames()) >= expected_min_log_num
                tar.extractall(dir_path)
                for gz in os.listdir(dir_path):
                    if "bootstrap" in gz:
                        BaseTest._verify_node_logs_uploaded(dir_path, gz)
                        BaseTest._verify_bootstrap_logs_uploaded(dir_path, gz, installation_success)
                    elif "master" in gz or "worker" in gz:
                        BaseTest._verify_node_logs_uploaded(dir_path, gz)
        finally:
            # clean up
            cluster_tar_path = os.path.abspath(cluster_tar_path)
            os.remove(cluster_tar_path)
            shutil.rmtree(dir_path)

    @staticmethod
    def _verify_node_logs_uploaded(dir_path, file_path):
        gz = tarfile.open(os.path.join(dir_path, file_path))
        logs = gz.getnames()
        for logs_type in ["agent.logs", "installer.logs", "mount.logs"]:
            assert any(logs_type in s for s in logs)
        gz.close()

    @staticmethod
    def _verify_bootstrap_logs_uploaded(dir_path, file_path, installation_success):
        gz = tarfile.open(os.path.join(dir_path, file_path))
        logs = gz.getnames()
        assert any("bootkube.logs" in s for s in logs)
        if not installation_success:
            for logs_type in ["dmesg.logs", "log-bundle"]:
                assert any(logs_type in s for s in logs)
            # test that installer-gather gathered logs from all masters
            lb_path = [s for s in logs if "log-bundle" in s][0]
            gz.extract(lb_path, dir_path)
            lb = tarfile.open(os.path.join(dir_path, lb_path))
            lb.extractall(dir_path)
            cp_path = [s for s in lb.getnames() if "control-plane" in s][0]
            assert len(os.listdir(os.path.join(dir_path, cp_path))) == env_variables["num_masters"]-1
            lb.close()
        gz.close()

    @staticmethod
    def verify_logs_are_current(started_cluster_install_at, logs_collected_at):
        for collected_at in logs_collected_at:
            # if host timestamp is set at all- check that the timestamp is from the last installation
            if collected_at > time.time() - 86400000:
                assert collected_at > started_cluster_install_at
