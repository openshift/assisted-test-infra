import logging
import os
import random
import yaml
from contextlib import suppress
from string import ascii_lowercase
from typing import Optional

import pytest
from assisted_service_client.rest import ApiException
from test_infra import consts, utils

from tests.conftest import env_variables


def random_name():
    return ''.join(random.choice(ascii_lowercase) for i in range(10))


class BaseTest:
    @pytest.fixture(scope="function")
    def node_controller(self, setup_node_controller):
        controller = setup_node_controller
        yield controller
        controller.shutdown_all_nodes()
        controller.format_all_node_disks()

    @pytest.fixture()
    def cluster(self, api_client):
        clusters = []

        def get_cluster_func(cluster_name: Optional[str] = None):
            if not cluster_name:
                cluster_name = random_name()

            res = api_client.create_cluster(cluster_name,
                                            ssh_public_key=env_variables['ssh_public_key'],
                                            openshift_version=env_variables['openshift_version'],
                                            pull_secret=env_variables['pull_secret'],
                                            base_dns_domain=env_variables['base_domain'],
                                            vip_dhcp_allocation=env_variables['vip_dhcp_allocation'])
            clusters.append(res)
            return res

        yield get_cluster_func

        for cluster in clusters:
            with suppress(ApiException):
                api_client.delete_cluster(cluster.id)

    @pytest.fixture()
    def clean(self, api_client):
        clusters = api_client.clusters_list()
        for cluster in clusters:
            api_client.delete_cluster(cluster['id'])

    def delete_cluster_if_exists(self, api_client, cluster_name):
        cluster_to_delete = self.get_cluster_by_name(
            api_client=api_client,
            cluster_name=cluster_name
        )

        if cluster_to_delete:
            api_client.delete_cluster(cluster_id=cluster_to_delete['id'])

    @staticmethod
    def get_cluster_by_name(api_client, cluster_name):
        clusters = api_client.clusters_list()
        for cluster in clusters:
            if cluster['name'] == cluster_name:
                return cluster
        return None

    @staticmethod
    def generate_and_download_image(
        cluster_id,
        api_client,
        iso_download_path=env_variables['iso_download_path'],
        ssh_key=env_variables['ssh_public_key']
    ):
        logging.info(iso_download_path)
        api_client.generate_and_download_image(
            cluster_id=cluster_id,
            ssh_key=ssh_key,
            image_path=iso_download_path
        )

    @staticmethod
    def wait_until_hosts_are_discovered(
        cluster_id,
        api_client,
        nodes_count=env_variables['num_nodes']
    ):
        utils.wait_till_all_hosts_are_in_status(
            client=api_client,
            cluster_id=cluster_id,
            nodes_count=nodes_count,
            statuses=[consts.NodesStatus.PENDING_FOR_INPUT, consts.NodesStatus.KNOWN]
        )

    @staticmethod
    def set_host_roles(cluster_id, api_client):
        utils.set_hosts_roles_based_on_requested_name(
            client=api_client,
            cluster_id=cluster_id
        )

    @staticmethod
    def set_network_params(
        cluster_id,
        api_client,
        controller,
        nodes_count=env_variables['num_nodes'],
        vip_dhcp_allocation=env_variables['vip_dhcp_allocation'],
        cluster_machine_cidr=env_variables['machine_cidr']
    ):
        if vip_dhcp_allocation:
            BaseTest.set_cluster_machine_cidr(cluster_id, api_client, cluster_machine_cidr)
        else:
            BaseTest.set_ingress_and_api_vips(cluster_id, api_client, controller)

        utils.wait_till_all_hosts_are_in_status(
            client=api_client,
            cluster_id=cluster_id,
            nodes_count=nodes_count,
            statuses=[consts.NodesStatus.KNOWN]
        )

    @staticmethod
    def set_cluster_machine_cidr(cluster_id, api_client, machine_cidr):
        logging.info(f'Setting Machine Network CIDR:{machine_cidr} for cluster: {cluster_id}')
        api_client.update_cluster(cluster_id, {"machine_network_cidr": machine_cidr})

    @staticmethod
    def set_ingress_and_api_vips(cluster_id, api_client, controller):
        vips = controller.get_ingress_and_api_vips()
        logging.info(f"Setting API VIP:{vips['api_vip']} and ingres VIP:{vips['ingress_vip']} for cluster: {cluster_id}")
        api_client.update_cluster(cluster_id, vips)

    @staticmethod
    def start_cluster_install(cluster_id, api_client):
        api_client.install_cluster(cluster_id=cluster_id)

    @staticmethod
    def cancel_cluster_install(cluster_id, api_client):
        api_client.cancel_cluster_install(cluster_id=cluster_id)

    @staticmethod
    def wait_for_installing_in_progress(cluster_id, api_client):
        utils.wait_till_at_least_one_host_is_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS]
        )

    @staticmethod
    def wait_for_one_host_to_boot_during_install(cluster_id, api_client):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=api_client,
            cluster_id=cluster_id,
            stages=[consts.HostsProgressStages.REBOOTING])

    @staticmethod
    def is_cluster_in_error_status(cluster_id, api_client):
        return utils.is_cluster_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.ERROR]
        )

    @staticmethod
    def is_cluster_in_cancelled_status(cluster_id, api_client):
        return utils.is_cluster_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.CANCELLED]
        )

    @staticmethod
    def reset_cluster_install(cluster_id, api_client):
        api_client.reset_cluster_install(cluster_id=cluster_id)

    @staticmethod
    def is_cluster_in_insufficient_status(cluster_id, api_client):
        return utils.is_cluster_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.INSUFFICIENT]
        )

    @staticmethod
    def is_hosts_in_wrong_boot_order(cluster_id, api_client):
        return utils.wait_till_all_hosts_are_in_status()

    @staticmethod
    def reboot_required_nodes_into_iso_after_reset(cluster_id, api_client, controller):
        nodes_to_reboot = api_client.get_hosts_in_statuses(
            cluster_id=cluster_id,
            statuses=[consts.NodesStatus.RESETING_PENDING_USER_ACTION]
        )
        for node in nodes_to_reboot:
            node_name = node["requested_hostname"]
            controller.shutdown_node(node_name)
            controller.format_node_disk(node_name)
            controller.start_node(node_name)

    @staticmethod
    def wait_until_cluster_is_ready_for_install(cluster_id, api_client):
        utils.wait_till_cluster_is_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.READY]
        )

    @staticmethod
    def wait_for_cluster_to_install(cluster_id, api_client, timeout=consts.CLUSTER_INSTALLATION_TIMEOUT):
        utils.wait_till_cluster_is_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.INSTALLED],
            timeout=timeout,
        )

    @staticmethod
    def wait_for_nodes_to_install(
        cluster_id,
        api_client,
        nodes_count=env_variables['num_nodes'],
        timeout=consts.CLUSTER_INSTALLATION_TIMEOUT
    ):
        utils.wait_till_all_hosts_are_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.INSTALLED],
            nodes_count=nodes_count,
            timeout=timeout,
        )
    
    @staticmethod
    def get_cluster_install_config(cluster_id, api_client):
        return yaml.load(api_client.get_cluster_install_config(cluster_id), Loader=yaml.SafeLoader)
