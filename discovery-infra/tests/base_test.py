import logging
import os
import random
import yaml
from contextlib import suppress
from string import ascii_lowercase
from typing import Optional
from collections import Counter

import pytest
from assisted_service_client.rest import ApiException
from test_infra import consts, utils
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.nodes import Nodes
from tests.conftest import env_variables


def random_name():
    return ''.join(random.choice(ascii_lowercase) for i in range(10))


class BaseTest:

    @pytest.fixture(scope="function")
    def nodes(self, setup_node_controller):
        controller = setup_node_controller
        nodes = Nodes(controller, env_variables["private_ssh_key_path"])
        nodes.set_correct_boot_order()
        yield nodes
        nodes.shutdown_all()
        nodes.format_all()

    @pytest.fixture()
    def cluster(self, api_client):
        clusters = []

        def get_cluster_func(cluster_name: Optional[str] = None):
            if not cluster_name:
                cluster_name = random_name()

            res = Cluster(api_client=api_client, cluster_name=cluster_name)
            clusters.append(res)
            return res

        yield get_cluster_func

        for cluster in clusters:
            logging.info(f'--- TEARDOWN --- deleting created cluster {cluster.id}')
            with suppress(ApiException):
                cluster.delete()

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
    def wait_until_hosts_are_registered(
        cluster_id,
        api_client,
        nodes_count=env_variables['num_masters']+env_variables['num_workers']
    ):
        utils.wait_till_all_hosts_are_in_status(
            client=api_client,
            cluster_id=cluster_id,
            nodes_count=nodes_count,
            statuses=[consts.NodesStatus.PENDING_FOR_INPUT,
                      consts.NodesStatus.INSUFFICIENT,
                      consts.NodesStatus.KNOWN,
            ]
        )

    @staticmethod
    def wait_until_hosts_are_discovered(
        cluster_id,
        api_client,
        nodes_count=env_variables['num_masters']+env_variables['num_workers']
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
        nodes_count=env_variables['num_masters']+env_variables['num_workers'],
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
    def wait_for_one_host_to_be_in_wrong_boot_order(cluster_id, api_client, fall_on_error_status=True):
        utils.wait_till_at_least_one_host_is_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            fall_on_error_status=fall_on_error_status,
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
    def disable_worker_nodes(cluster_id, api_client):
        hosts = api_client.get_cluster_hosts(cluster_id=cluster_id)
        for host in hosts:
            if host["role"] == consts.NodeRoles.WORKER:
                host_name = host["requested_hostname"]
                logging.info(f"Going to disable host: {host_name} in cluster: {cluster_id}")
                api_client.disable_host(cluster_id=cluster_id, host_id=host["id"])


    @staticmethod
    def is_cluster_in_insufficient_status(cluster_id, api_client):
        return utils.is_cluster_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.INSUFFICIENT]
        )

    @staticmethod
    def wait_until_cluster_is_ready_for_install(cluster_id, api_client):
        utils.wait_till_cluster_is_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.READY]
        )

    @staticmethod
    def wait_until_cluster_starts_installation(cluster_id, api_client):
        utils.wait_till_cluster_is_in_status(
            client=api_client,
            cluster_id=cluster_id,
            statuses=[consts.ClusterStatus.PREPARING_FOR_INSTALLATION,
                      consts.ClusterStatus.INSTALLING,
                      consts.ClusterStatus.FINALIZING]
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
        nodes_count=env_variables['num_masters']+env_variables['num_workers'],
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


    @staticmethod
    def wait_for_nodes_status_installing_or_installed(
            cluster_id,
            api_client,
            nodes_count=env_variables['num_masters']+env_variables['num_workers']):
        utils.wait_till_all_hosts_are_in_status(
            client=api_client,
            cluster_id=cluster_id,
            nodes_count=nodes_count,
            statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS,
                      consts.NodesStatus.INSTALLED],
            interval=30,
        )

    def setup_hosts(self, cluster_id, api_client, nodes):
        self.generate_and_download_image(cluster_id=cluster_id,
                                         api_client=api_client)
        nodes.start_all()
        self.wait_until_hosts_are_registered(cluster_id=cluster_id,
                                             api_client=api_client)
        return api_client.get_cluster_hosts(cluster_id=cluster_id)

    def expect_ready_to_install(self, cluster_id, api_client):
        self.wait_until_cluster_is_ready_for_install(cluster_id=cluster_id,
                                                     api_client=api_client)
    
    def start_installation(self, cluster_id, api_client):
        self.start_cluster_install(cluster_id=cluster_id,
                                   api_client=api_client)
        self.wait_until_cluster_starts_installation(cluster_id=cluster_id,
                                                    api_client=api_client)
        hosts = api_client.get_cluster_hosts(cluster_id=cluster_id)
        return {h["id"]: h["role"] for h in hosts}

    def _get_matching_hosts(self, hosts, host_type, count):
        return [{"id": h["id"], "role": host_type}
                for h in hosts
                if host_type in h["requested_hostname"]][:count]
    
    def assign_roles(self, cluster_id, api_client, hosts, requested_roles):
        assigned_roles = self._get_matching_hosts(
            hosts=hosts,
            host_type=consts.NodeRoles.MASTER,
            count=requested_roles["master"])

        assigned_roles.extend(self._get_matching_hosts(
            hosts=hosts,
            host_type=consts.NodeRoles.WORKER,
            count=requested_roles["worker"]))

        api_client.set_hosts_roles(
            cluster_id=cluster_id,
            hosts_with_roles=assigned_roles)

        return assigned_roles
