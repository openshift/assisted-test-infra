import pytest
import os
import time
import tarfile
import logging

from test_infra import utils
from assisted_service_client.rest import ApiException
from tests.base_test import BaseTest


class TestDownloadLogs(BaseTest):
    def setup_hosts(self, cluster_id, api_client, nodes):
        '''setup nodes from ISO image and wait until they are registered'''
        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Boot nodes into ISO
        nodes.start_all()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)

    def prepare_for_installation(self, cluster_id, api_client, nodes):
        '''set roles and network params to prepare the cluster for install'''
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(cluster_id=cluster_id,
                                api_client=api_client,
                                controller=nodes.controller
                                )

    def install_cluster_and_wait(self, cluster_id, api_client):
        '''start the cluster and wait for host to go to installing-in-progress state'''
        # Start cluster install
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # wait until all nodes are in Installed status, and the cluster moved to status installed
        self.wait_for_nodes_to_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

    def reset_cluster_and_wait(self, cluster_obj, api_client, nodes):
        # Reset cluster install
        self.reset_cluster_install(cluster_id=cluster_obj.id, api_client=api_client)
        assert self.is_cluster_in_insufficient_status(
            cluster_id=cluster_obj.id,
            api_client=api_client
        )
        # Reboot required nodes into ISO
        cluster_obj.reboot_required_nodes_into_iso_after_reset(nodes)
        # Wait for hosts to be rediscovered
        self.wait_until_hosts_are_discovered(cluster_id=cluster_obj.id, api_client=api_client)
        self.wait_until_cluster_is_ready_for_install(cluster_id=cluster_obj.id, api_client=api_client)

    def test_collect_logs_on_success(self, api_client, nodes, cluster):
        # Define new cluster and prepare it for installation
        cluster_id = cluster().id
        self.setup_hosts(cluster_id, api_client, nodes)
        self.prepare_for_installation(cluster_id, api_client, nodes)

        # download logs into a file. At this point logs are not uploaded
        path = "/tmp/test_on-success_logs.tar"
        self.verify_no_logs_uploaded(cluster_id, api_client, path)

        # install the cluster
        started_cluster_install_at = time.time()
        self.install_cluster_and_wait(cluster_id, api_client)

        # download logs into a file. At this point we are expecting to have logs from each
        # host plus controller logs
        logs_collected_at = utils.get_logs_collected_at(api_client, cluster_id)
        expected_min_log_num = len(nodes) + 1
        self.verify_logs_uploaded(cluster_id, api_client, path, expected_min_log_num)
        self.verify_logs_are_current(started_cluster_install_at, logs_collected_at)

    @pytest.mark.regression
    def test_collect_logs_on_failure(self, api_client, nodes, cluster):
        '''cancel insllation after at least one host is booted and check that logs are uploaded'''
        # Define new cluster and prepare it for installation
        '''starting first installation'''
        cluster_id = cluster().id
        self.setup_hosts(cluster_id, api_client, nodes)
        self.prepare_for_installation(cluster_id, api_client, nodes)

        started_cluster_install_at = time.time()
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # Cancel cluster install once at least one host has been rebooted
        self.wait_for_one_host_to_boot_during_install(cluster_id=cluster_id, api_client=api_client)
        self.cancel_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_cancelled_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # download logs into a file. At this point logs exist and we expect them to
        # be from the hosts that finished reboot without controller logs
        '''verify logs are uploaded during the first installation'''
        path = "/tmp/test_on_restart_logs.tar"
        expected_min_log_num = 1
        self.verify_logs_uploaded(cluster_id, api_client, path, expected_min_log_num)

        # reset cluster and that boot the hosts again from ISO and wait for re-discovery
        '''reset cluster and reboot hosts'''
        self.reset_cluster_and_wait(cluster(), api_client, nodes)
        # re-install the cluster
        '''second installation'''
        started_cluster_install_at = time.time()
        self.install_cluster_and_wait(cluster_id, api_client)

        # verify that the logs are current after re-install and were not left from
        # the previous attempt
        '''verify second upload of logs'''
        logs_collected_at = utils.get_logs_collected_at(api_client, cluster_id)
        expected_min_log_num = len(nodes) + 1
        self.verify_logs_uploaded(cluster_id, api_client, path, expected_min_log_num)
        self.verify_logs_are_current(started_cluster_install_at, logs_collected_at)

    def verify_no_logs_uploaded(self, cluster_id, api_client, path):
        with pytest.raises(ApiException) as ex:
            api_client.download_cluster_logs(cluster_id, path)
        assert "No log files" in str(ex.value)

    def verify_logs_uploaded(self, cluster_id, api_client, path, expected_min_log_num):
        # download logs
        api_client.download_cluster_logs(cluster_id, path)
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

    def verify_logs_are_current(self, started_cluster_install_at, logs_collected_at):
        for collected_at in logs_collected_at:
            # if host timestamp is set at all- check that the timestamp is from the last installation
            if collected_at > time.time() - 86400000:
                assert collected_at > started_cluster_install_at
