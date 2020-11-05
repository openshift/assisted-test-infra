import logging
import pytest

from netaddr import IPNetwork

from tests.base_test import BaseTest
from tests.conftest import env_variables
from assisted_service_client.rest import ApiException


logger = logging.getLogger(__name__)


class TestCancelReset(BaseTest):
    @pytest.mark.regression
    def test_cancel_reset_before_node_boot(self, api_client, node_controller, cluster):
        # Define new cluster
        new_cluster = cluster()
        new_cluster.prepare_for_install(controller=node_controller)
        # Start cluster install
        new_cluster.start_install()
        # Cancel cluster install once cluster installation start
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status()
        # Reset cluster install
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        new_cluster.reboot_required_nodes_into_iso_after_reset(controller=node_controller)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        # TODO need to think how to test it and make it quick
        # new_cluster.start_install()
        # # wait until all nodes are in Installed status, will fail in case one host in error
        # new_cluster.wait_for_nodes_to_install()
        # new_cluster.wait_for_install()


    @pytest.mark.regression
    def test_cancel_reset_after_node_boot(self, api_client, node_controller, cluster):
        cluster_id = cluster().id
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        node_controller.start_all_nodes()
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # Cancel cluster install once at least one host booted
        self.wait_for_one_host_to_boot_during_install(cluster_id=cluster_id, api_client=api_client)
        self.cancel_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_cancelled_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # Reset cluster install
        self.reset_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_insufficient_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # Reboot required nodes into ISO
        self.reboot_required_nodes_into_iso_after_reset(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )
        # Wait for hosts to be rediscovered
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.wait_until_cluster_is_ready_for_install(cluster_id=cluster_id, api_client=api_client)
        # TODO need to think how to test it and make it quick
        # # Install Cluster
        # self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # self.wait_for_nodes_to_install(cluster_id=cluster_id, api_client=api_client)
        # self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

    @pytest.mark.regression
    def test_cancel_reset_one_node_unavailable(self, api_client, node_controller, cluster):
        cluster_id = cluster().id
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        node_controller.start_all_nodes()
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # Cancel cluster install once cluster installation start
        self.wait_for_installing_in_progress(cluster_id=cluster_id, api_client=api_client)
        self.cancel_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_cancelled_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # Shutdown one node
        nodes = node_controller.list_nodes()
        node = nodes[0]
        node.shutdown()
        # Reset cluster install
        self.reset_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_insufficient_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # Reboot required nodes into ISO
        self.reboot_required_nodes_into_iso_after_reset(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )
        # Wait for hosts to be rediscovered
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.wait_until_cluster_is_ready_for_install(cluster_id=cluster_id, api_client=api_client)
        # TODO need to think how to test it and make it quick
        # # Install Cluster
        # self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # self.wait_for_nodes_to_install(cluster_id=cluster_id, api_client=api_client)
        # self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

    @pytest.mark.regression
    def test_cancel_reset_while_disable_workers(self, api_client, node_controller, cluster):
        cluster_id = cluster().id
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        node_controller.start_all_nodes()
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )
        self.disable_worker_nodes(cluster_id=cluster_id, api_client=api_client)
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # Cancel cluster install once cluster installation start
        self.wait_for_installing_in_progress(cluster_id=cluster_id, api_client=api_client)
        self.cancel_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_cancelled_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # Reset cluster install
        self.reset_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_insufficient_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
        # Reboot required nodes into ISO
        self.reboot_required_nodes_into_iso_after_reset(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )
        # Wait for hosts to be rediscovered
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id,
                                             api_client=api_client,
                                             nodes_count=env_variables['num_masters'])
        self.wait_until_cluster_is_ready_for_install(cluster_id=cluster_id, api_client=api_client)
        # Install Cluster
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_nodes_to_install(cluster_id=cluster_id,
                                       api_client=api_client,
                                       nodes_count=env_variables['num_masters'])
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

    @pytest.mark.regression
    def test_reset_cluster_while_at_least_one_node_finished_installation(
        self,
        api_client,
        node_controller,
        cluster
    ):
        new_cluster = cluster()
        logger.debug(
            'Cluster ID for '
            'test_reset_cluster_while_at_least_one_node_finished_installation'
            'is %s', new_cluster.id
        )
        new_cluster.prepare_for_install(node_controller)
        new_cluster.start_install()
        new_cluster.wait_for_nodes_to_install(nodes_count=1)
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status(), \
            f'cluster {new_cluster.id} failed to cancel after at least one ' \
            f'host has finished installation'
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status(), \
            f'cluster {new_cluster.id} failed to reset from canceled state'
        new_cluster.reboot_required_nodes_into_iso_after_reset(node_controller)
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # new_cluster.start_install()
        # new_cluster.wait_for_nodes_to_install()
        # new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cluster_install_and_reset_10_times(
            self,
            api_client,
            node_controller,
            cluster
    ):
        new_cluster = cluster()
        logger.debug(
            'Cluster ID for '
            'test_cluster_install_and_reset_10_times is %s', new_cluster.id
        )
        new_cluster.prepare_for_install(node_controller)
        for i in range(10):
            logger.debug(
                'test_cluster_install_and_reset_10_times attempt number: %d',
                i + 1
            )
            new_cluster.start_install()
            new_cluster.wait_for_nodes_to_install(nodes_count=1)
            new_cluster.cancel_install()
            assert new_cluster.is_in_cancelled_status(), \
                f'cluster {new_cluster.id} failed to cancel after on attempt ' \
                f'number: {i}'
            new_cluster.reset_install()
            assert new_cluster.is_in_insufficient_status(), \
                f'cluster {new_cluster.id} failed to reset from on attempt ' \
                f'number: {i}'
            new_cluster.reboot_required_nodes_into_iso_after_reset(
                node_controller)
            new_cluster.wait_until_hosts_are_discovered()
            new_cluster.wait_for_ready_to_install()

        new_cluster.start_install()
        new_cluster.wait_for_nodes_to_install()
        new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_reset_cluster_after_successful_installation(
            self,
            api_client,
            node_controller,
            cluster
    ):
        new_cluster = cluster()
        logger.debug(
            'Cluster ID for '
            'test_reset_cluster_while_at_least_one_node_finished_installation'
            'is %s', new_cluster.id
        )

        new_cluster.prepare_for_install(node_controller)
        new_cluster.start_install()
        new_cluster.wait_for_nodes_to_install()
        new_cluster.wait_for_install()

        with pytest.raises(ApiException):
            # TODO: catch the specific error code
            new_cluster.cancel_install()

        with pytest.raises(ApiException):
            # TODO: catch the specific error code
            new_cluster.reset_install()

    # TODO: Finish test
    @pytest.mark.skip
    def test_reset_cluster_after_changing_cluster_configuration(
            self,
            api_client,
            node_controller,
            cluster
    ):
        new_cluster = cluster()
        logger.debug(
            'Cluster ID for '
            'test_reset_cluster_after_changing_cluster_configuration is %s',
            new_cluster.id
        )

        new_cluster.prepare_for_install(node_controller)
        new_cluster.start_install()
        new_cluster.wait_for_nodes_to_install(nodes_count=1)
        new_cluster.cancel_install()
        assert new_cluster.is_in_cancelled_status(), \
            f'cluster {new_cluster.id} failed to cancel'
        new_cluster.reset_install()
        assert new_cluster.is_in_insufficient_status(), \
            f'cluster {new_cluster.id} failed to reset from canceled state'
        vips = node_controller.get_ingress_and_api_vips()
        api_vip = IPNetwork(vips['api_vip'])
        api_vip += 1
        ingress_vip = IPNetwork(vips['ingress_vip'])
        ingress_vip += 1

        self.client.update_params(
            new_cluster.id,
            {
                'api_vip': str(api_vip),
                'ingress_vip': str(ingress_vip),
                #'pull_secret': # TODO: COMPLETE
            }
        )

        new_cluster.start_install()
        new_cluster.wait_for_nodes_to_install()
        new_cluster.wait_for_install()

