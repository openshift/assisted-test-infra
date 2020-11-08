import logging
import pytest

from netaddr import IPNetwork
from test_infra import consts
from tests.base_test import BaseTest
from assisted_service_client.rest import ApiException


logger = logging.getLogger(__name__)


class TestCancelReset(BaseTest):
    @pytest.mark.regression
    def test_cancel_reset_before_node_boot(self, env, api_client, node_controller, cluster):
        node_controller = node_controller(env)
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
    def test_cancel_reset_after_node_boot(self, env, api_client, node_controller, cluster):
        node_controller = node_controller(env)
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
    def test_cancel_reset_one_node_unavailable(self, env, api_client, node_controller, cluster):
        node_controller = node_controller(env)
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
    def test_cancel_reset_while_disable_workers(self, env, api_client, node_controller, cluster):
        node_controller = node_controller(env)
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
                                             nodes_count=env['num_masters'])
        self.wait_until_cluster_is_ready_for_install(cluster_id=cluster_id, api_client=api_client)
        # Install Cluster
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_nodes_to_install(cluster_id=cluster_id,
                                       api_client=api_client,
                                       nodes_count=env['num_masters'])
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

    @pytest.mark.regression
    def test_reset_cluster_while_at_least_one_node_finished_installation(
        self,
        env,
        api_client,
        node_controller,
        cluster
    ):
        node_controller = node_controller(env)
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
            env,
            api_client,
            node_controller,
            cluster
    ):
        node_controller = node_controller(env)
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
            env,
            api_client,
            node_controller,
            cluster
    ):
        node_controller = node_controller(env)
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
            env,
            api_client,
            node_controller,
            cluster
    ):
        node_controller = node_controller(env)
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

    @pytest.mark.regression
    def test_cancel_reset_after_installation_failure(self, env, api_client, node_controller, cluster):
        node_controller = node_controller(env)
        # Define new cluster
        new_cluster = cluster()
        new_cluster.prepare_for_install(controller=node_controller)
        # Start cluster install
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress(nodes_count=env_variables['num_nodes'])
        # Kill bootstrap installer to simulate cluster error
        b_node_name = new_cluster.get_bootstrap_hostname()
        for node in node_controller.list_nodes():
            if node.name == b_node_name:
                node.kill_podman_container_by_name("assisted-installer")
                break
        # Wait for cluster state Error
        new_cluster.wait_for_cluster_in_error_status()
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
        # wait until all nodes are in Installed status, will fail in case one host in error
        # new_cluster.wait_for_nodes_to_install()
        # new_cluster.wait_for_install()

    @pytest.mark.regression
    def test_cancel_reset_after_installation_failure_and_wrong_boot(self,
                                                                    env,
                                                                    api_client,
                                                                    node_controller,
                                                                    cluster):
        node_controller = node_controller(env)
        # Define new cluster
        new_cluster = cluster()
        # Change boot order to a master node
        hosts = node_controller.list_nodes_with_name_filter(consts.NodeRoles.MASTER)
        selected_master = hosts[0]
        selected_master.set_boot_order(cd_first=True)
        # Start cluster install
        new_cluster.prepare_for_install(controller=node_controller)
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress(nodes_count=env_variables['num_nodes'])
        # Kill worker installer to simulate host error
        worker_nodes = new_cluster.get_nodes_by_role(consts.NodeRoles.WORKER)
        selected_worker = worker_nodes[0]
        nodes = node_controller.list_nodes()
        for node in nodes:
            if selected_worker["requested_hostname"] == node.name:
                node.kill_podman_container_by_name("assisted-installer")
                break
        # Wait for node Error
        new_cluster.wait_for_node_status([consts.NodesStatus.ERROR])
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
        new_cluster.reboot_required_nodes_into_iso_after_reset(controller=node_controller)
        # Wait for hosts to be rediscovered
        new_cluster.wait_until_hosts_are_discovered()
        new_cluster.wait_for_ready_to_install()
        # Install Cluster
        # TODO need to think how to test it and make it quick
        # new_cluster.start_install()
        # wait until all nodes are in Installed status, will fail in case one host in error
        # new_cluster.wait_for_nodes_to_install()
        # new_cluster.wait_for_install()
