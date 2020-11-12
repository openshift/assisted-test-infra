import pytest
import os
import time
import tarfile
import logging

from test_infra import utils
from assisted_service_client.rest import ApiException
from tests.base_test import BaseTest


class TestDownloadLogs(BaseTest):
    def _reset_cluster_and_wait_for_ready(self, cluster, nodes):
        # Reset cluster install
        cluster.reset_install()
        assert cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        cluster.wait_until_hosts_are_discovered()
        cluster.wait_for_ready_to_install()

    @pytest.mark.regression
    def test_collect_logs_on_success(self, api_client, nodes, cluster):
        # Define new cluster and prepare it for installation
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        # download logs into a file. At this point logs are not uploaded
        path = "/tmp/test_on-success_logs.tar"
        self._verify_no_logs_uploaded(new_cluster, path)

        # install the cluster
        started_cluster_install_at = time.time()
        new_cluster.start_install_and_wait_for_installed()
        # download logs into a file. At this point we are expecting to have logs from each
        # host plus controller logs
        logs_collected_at = utils.get_logs_collected_at(api_client, new_cluster.id)
        expected_min_log_num = len(nodes) + 1
        new_cluster.download_installation_logs(path)
        self._verify_logs_uploaded(path, expected_min_log_num)
        self._verify_logs_are_current(started_cluster_install_at, logs_collected_at)

    @pytest.mark.regression
    def test_collect_logs_on_failure(self, api_client, nodes, cluster):
        '''cancel insllation after at least one host is booted and check that logs are uploaded'''
        # Define new cluster and prepare it for installation
        '''starting first installation'''
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        started_cluster_install_at = time.time()
        new_cluster.start_install()
        # Cancel cluster install once at least one host has been rebooted
        new_cluster.wait_for_at_least_one_host_to_boot_during_install()
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # download logs into a file. At this point logs exist and we expect them to
        # be from the hosts that finished reboot without controller logs
        '''verify logs are uploaded during the first installation'''
        path = "/tmp/test_on_restart_logs.tar"
        expected_min_log_num = 1
        new_cluster.download_installation_logs(path)
        self._verify_logs_uploaded(path, expected_min_log_num)
        # reset cluster and that boot the hosts again from ISO and wait for re-discovery
        self._reset_cluster_and_wait_for_ready(new_cluster, nodes)
        # re-install the cluster
        started_cluster_install_at = time.time()
        new_cluster.start_install_and_wait_for_installed()
        # verify that the logs are current after re-install and were not left from
        # the previous attempt
        '''verify second upload of logs'''
        logs_collected_at = utils.get_logs_collected_at(api_client, new_cluster.id)
        expected_min_log_num = len(nodes) + 1
        new_cluster.download_installation_logs(path)
        self._verify_logs_uploaded(path, expected_min_log_num)
        self._verify_logs_are_current(started_cluster_install_at, logs_collected_at)

    def _verify_no_logs_uploaded(self, cluster, path):
        with pytest.raises(ApiException) as ex:
            cluster.download_installation_logs(path)
        assert "No log files" in str(ex.value)

    def _verify_logs_uploaded(self, path, expected_min_log_num):
        # verify that logs were collected from all expected sources
        assert (os.path.exists(path))
        try:
            tar = tarfile.open(path)
            logging.info(f'downloaded logs: {tar.getnames()}')
            assert len(tar.getnames()) >= expected_min_log_num
            tar.close()
        finally:
            # clean up
            os.remove(path)

    def _verify_logs_are_current(self, started_cluster_install_at, logs_collected_at):
        for collected_at in logs_collected_at:
            # if host timestamp is set at all- check that the timestamp is from the last installation
            if collected_at > time.time() - 86400000:
                assert collected_at > started_cluster_install_at
