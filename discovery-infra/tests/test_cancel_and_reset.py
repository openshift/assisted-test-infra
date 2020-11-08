import logging
import pytest

from netaddr import IPNetwork
from test_infra import consts
from tests.base_test import BaseTest
from tests.conftest import env_variables
from assisted_service_client.rest import ApiException


logger = logging.getLogger(__name__)

DUMMY_SSH_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj+lurtXW2WxojtNXSxEWWTmkm1VLzAj/" \
                "9Mhz4W1jCPkiLBrelT+DeuCzFHhTW01GJ8o5qCl2hG1R1SUrICmry6CsCnZErdotJLw1eDY" \
                "TuBvGSNoZGxeRAgu7XsgJLQcxVRx1a9AmI9nwu/tPXKm6Rsg9uY65DabcL/uXXqfyfiOjXX" \
                "i/fbkVhPfNTxKL5yH5ulqa4HOdpg/hKHOQSVg1/BeU5reAB0LWiKURPofkkR3vNuI+Vf2Ew" \
                "IX7n2upNmP6BdUHmKFkM4k4yXcSFSKbMkMDb2plZPi48ctagrGPI/N0m3nyEvdw3HA358IZ" \
                "ssMM2gE7AYdBgVL/QEAILFBdvDKGCNNYX+EQ3umr5CkJXPZFbFVMDLvp2wOwCw5ysWjj33m" \
                "d0Nb7u4/7cpvXnVmrskiqCjkxAsUWh+D4vvASYAsxl5OFhhst6EQG3C07EHGE6FHXCfP54b" \
                "z6RyQIUSSUeHGFH9PeE0t8nuNVvfp4V7X0SoJbP+jYfcyo5OYtQbXs= root@test." \
                "ocp-cluster.lab.eng.tlv2.redhat.com.com"


class TestCancelReset(BaseTest):
    @pytest.mark.sanity
    def test_cancel_reset_before_node_boot(self, api_client, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        # Start cluster install
        new_cluster.start_install()
        # Cancel cluster install once cluster installation start
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        new_cluster.start_install()
        # wait until all nodes are in Installed status, will fail in case one host in error
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cancel_reset_after_node_boot(self, api_client, nodes, cluster):
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        # Cancel cluster install once at least one host booted
        new_cluster.wait_for_at_least_one_host_to_boot_during_install()
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cancel_reset_one_node_unavailable(self, api_client, nodes, cluster):
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        # Cancel cluster install once cluster installation start
        new_cluster.wait_for_installing_in_progress(nodes_count=2)
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # Shutdown one node
        node = nodes.get_random_node()
        node.shutdown()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cancel_reset_while_disable_workers(self, api_client, nodes, cluster):
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.disable_worker_hosts()
        new_cluster.start_install()
        # Cancel cluster install once cluster installation start
        new_cluster.wait_for_installing_in_progress(nodes_count=2)
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered(nodes_count=env_variables['num_masters'])
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install(nodes_count=env_variables['num_masters'])
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_reset_cluster_while_at_least_one_node_finished_installation(self,
                                                                         api_client,
                                                                         nodes,
                                                                         cluster):
        new_cluster = cluster()
        logger.debug(f'Cluster ID for '
                     f'test_reset_cluster_while_at_least_one_node_finished_installation is '
                     f'{new_cluster.id}')
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install(nodes_count=1)
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status(), \
            f'cluster {new_cluster.id} failed to cancel after at least one ' \
            f'host has finished installation'
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status(), \
            f'cluster {new_cluster.id} failed to reset from canceled state'
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    @pytest.mark.skip
    def test_cluster_install_and_reset_10_times(self,
                                                api_client,
                                                nodes,
                                                cluster):
        new_cluster = cluster()
        logger.debug(f'Cluster ID for test_cluster_install_and_reset_10_times is'
                     f' {new_cluster.id}')
        new_cluster.prepare_for_install(nodes=nodes)
        for i in range(10):
            logger.debug(f'test_cluster_install_and_reset_10_times attempt number: {i + 1}')
            new_cluster.start_install()
            new_cluster.wait_for_write_image_to_disk(nodes_count=2)
            new_cluster.cancel_install()
            assert new_cluster.is_in_cancelled_status(), \
                f'cluster {new_cluster.id} failed to cancel after on attempt ' \
                f'number: {i}'
            new_cluster.reset_install()
            assert new_cluster.is_in_insufficient_status(), \
                f'cluster {new_cluster.id} failed to reset from on attempt ' \
                f'number: {i}'
            new_cluster.reboot_required_nodes_into_iso_after_reset(
                nodes=nodes)
            new_cluster.wait_until_hosts_are_discovered()
            new_cluster.wait_for_ready_to_install()

        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_reset_cluster_after_successful_installation(
            self,
            api_client,
            nodes,
            cluster):
        new_cluster = cluster()
        logger.debug(f'Cluster ID for '
                     f'test_reset_cluster_while_at_least_one_node_finished_installation is'
                     f' {new_cluster.id}')
        new_cluster.prepare_for_install(nodes)
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

        with pytest.raises(ApiException):
            # TODO: catch the specific error code
            new_cluster.cancel_install()

        with pytest.raises(ApiException):
            # TODO: catch the specific error code
            new_cluster.reset_install()

    @pytest.mark.regression
    def test_reset_cluster_after_changing_cluster_configuration(
            self,
            api_client,
            nodes,
            cluster):
        new_cluster = cluster()
        logger.debug(
            'Cluster ID for '
            'test_reset_cluster_after_changing_cluster_configuration is %s',
            new_cluster.id
        )

        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install(nodes_count=1)
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status(), \
            f'cluster {new_cluster.id} failed to cancel'
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status(), \
            f'cluster {new_cluster.id} failed to reset from canceled state'
        vips = nodes.controller.get_ingress_and_api_vips()
        api_vip = IPNetwork(vips['api_vip'])
        api_vip += 1
        ingress_vip = IPNetwork(vips['ingress_vip'])
        ingress_vip += 1
        api_vip = str(api_vip).split("/")[0]
        ingress_vip = str(ingress_vip).split("/")[0]
        new_cluster.set_ingress_and_api_vips({
                'api_vip': api_vip,
                'ingress_vip': ingress_vip})
        new_cluster.set_ssh_key({'ssh_public_key': DUMMY_SSH_KEY})
        new_cluster.reboot_required_nodes_into_iso_after_reset(
            nodes)
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        new_cluster.start_install()
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cancel_reset_after_installation_failure(self, api_client, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()
        new_cluster.prepare_for_install(nodes=nodes)
        # Start cluster install
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress(nodes_count=env_variables['num_nodes'])
        # Kill bootstrap installer to simulate cluster error
        b_node_name = new_cluster.get_bootstrap_hostname()
        bootstrap = nodes.get_bootstrap_node(cluster=new_cluster)
        bootstrap.kill_podman_container_by_name("assisted-installer")
        # Wait for cluster state Error
        new_cluster.wait_for_cluster_in_error_status()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        new_cluster.start_install()
        # wait until all nodes are in Installed status, will fail in case one host in error
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cancel_reset_after_installation_failure_and_wrong_boot(self,
                                                                    api_client,
                                                                    nodes,
                                                                    cluster):
        # Define new cluster
        new_cluster = cluster()
        # Change boot order to a master node
        selected_master = nodes.get_masters()[0]
        nodes.set_wrong_boot_order(selected_master)
        # Start cluster install
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress(nodes_count=env_variables['num_nodes'])
        # Kill worker installer to simulate host error
        worker_host = new_cluster.get_hosts_by_role(consts.NodeRoles.WORKER)[0]
        selected_worker_node = nodes.get_node_from_cluster_host(worker_host)
        selected_worker_node.kill_podman_container_by_name("assisted-installer")
        # Wait for node Error
        new_cluster.wait_for_host_status([consts.NodesStatus.ERROR])
        # Wait for wong boot order
        new_cluster.wait_for_one_host_to_be_in_wrong_boot_order(fall_on_error_status=False)
        # Cancel cluster install once cluster installation start
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Fix boot order and reboot required nodes into ISO
        selected_master.set_boot_order(cd_first=False)
        new_cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        new_cluster.start_install()
        # wait until all nodes are in Installed status, will fail in case one host in error
        new_cluster.wait_for_hosts_to_install()
        new_cluster.wait_for_install()
