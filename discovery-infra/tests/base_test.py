import json
import logging
import os
import shutil
from collections import Callable
from contextlib import suppress
from pathlib import Path

import pytest

import test_infra.utils as infra_utils
import waiting
from assisted_service_client.rest import ApiException
from download_logs import download_logs
from junit_report import JunitFixtureTestCase, JunitTestCase
from paramiko import SSHException
from test_infra import consts
from tests.config import ClusterConfig, EnvConfig
from test_infra.controllers.proxy_controller.proxy_controller import ProxyController
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.kube_helpers import create_kube_api_client, KubeAPIContext
from test_infra.helper_classes.nodes import Nodes
from test_infra.tools.assets import NetworkAssets
from tests.config import TerraformConfig
from tests.conftest import env_variables
from test_infra.controllers.node_controllers import TerraformController


class BaseTest:

    @pytest.fixture(scope="function")
    @JunitFixtureTestCase()
    def get_nodes(self) -> Callable:
        """ Currently support only single instance of nodes """
        nodes_data = dict()

        def get_nodes_func(config: TerraformConfig = TerraformConfig()):

            nodes_data["needs_nat"] = config.platform == consts.Platforms.NONE
            nodes_data["net_asset"] = NetworkAssets()
            config.net_asset = nodes_data["net_asset"].get()

            nodes = Nodes(TerraformController(config), config.private_ssh_key_path)
            nodes.prepare_nodes()
            if nodes_data["needs_nat"]:
                nodes_data["nodes"].configure_nat()

            nodes_data["nodes"] = nodes
            return nodes

        yield get_nodes_func

        try:
            if EnvConfig.get("test_teardown"):
                logging.info('--- TEARDOWN --- node controller\n')
                nodes_data.get("nodes").destroy_all_nodes()
            if nodes_data.get("needs_nat"):
                nodes_data.get("nodes").unconfigure_nat()
        finally:
            nodes_data.get("net_asset").release_all()

    @pytest.fixture()
    @JunitFixtureTestCase()
    def get_cluster(self, api_client, request, get_nodes) -> Callable:
        clusters = []

        @JunitTestCase()
        def get_cluster_func(nodes: Nodes, cluster_config: ClusterConfig = ClusterConfig()):
            if not cluster_config.cluster_name:
                cluster_config.cluster_name = env_variables.get('cluster_name', infra_utils.get_random_name(length=10))
            res = Cluster(api_client=api_client, config=cluster_config, nodes=nodes)
            clusters.append(res)
            return res

        yield get_cluster_func
        for cluster in clusters:
            if request.node.result_call.failed:
                logging.info(f'--- TEARDOWN --- Collecting Logs for test: {request.node.name}\n')
                self.collect_test_logs(cluster, api_client, request.node, cluster.nodes)
            if env_variables['test_teardown']:
                if cluster.is_installing() or cluster.is_finalizing():
                    cluster.cancel_install()
                with suppress(ApiException):
                    logging.info(f'--- TEARDOWN --- deleting created cluster {cluster.id}\n')
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
                iso_download_path=env_variables['iso_download_path']
        ):

            given_node_ips = []
            if download_image:
                cluster.generate_and_download_image(
                    iso_download_path=iso_download_path,
                )
            nodes.start_given(given_nodes)
            for node in given_nodes:
                given_node_ips.append(node.ips[0])
            nodes.shutdown_given(given_nodes)

            logging.info(f'Given node ips: {given_node_ips}')

            for _rule in iptables_rules:
                _rule.add_sources(given_node_ips)
                rules.append(_rule)
                _rule.insert()

        yield set_iptables_rules_for_nodes
        logging.info('---TEARDOWN iptables ---')
        for rule in rules:
            rule.delete()

    @staticmethod
    def attach_disk_flags(persistent):
        modified_nodes = set()

        def attach(node, disk_size, bootable=False, with_wwn=False):
            nonlocal modified_nodes
            node.attach_test_disk(disk_size, bootable=bootable, persistent=persistent, with_wwn=with_wwn)
            modified_nodes.add(node)

        yield attach
        if env_variables['test_teardown']:
            for modified_node in modified_nodes:
                modified_node.detach_all_test_disks()

    @pytest.fixture(scope="function")
    def attach_disk(self):
        yield from self.attach_disk_flags(persistent=False)

    @pytest.fixture(scope="function")
    def attach_disk_persistent(self):
        yield from self.attach_disk_flags(persistent=True)

    @pytest.fixture()
    def attach_interface(self):
        added_networks = []

        def add(node, network_name=None, network_xml=None):
            interface_mac = ""
            network = ""
            if network_xml:
                network, interface_mac = node.attach_interface(network_xml)
            elif network_name:
                interface_mac = node.add_interface(network_name)
                network = node.get_network_by_name(network_name)
            added_networks.append({"node": node, "network": network, "mac": interface_mac})

        yield add
        for added_network in added_networks:
            logging.info(f'Deleting custom networks:{added_networks}')
            with suppress(Exception):
                node_obj = added_network.get("node")
                node_obj.undefine_interface(added_network.get("mac"))
                node_obj.destroy_network(added_network.get("network"))

    @pytest.fixture()
    def proxy_server(self):
        logging.info('--- SETUP --- proxy controller')
        proxy_servers = []

        def start_proxy_server(**kwargs):
            proxy_server = ProxyController(**kwargs)
            proxy_servers.append(proxy_server)

            return proxy_server

        yield start_proxy_server
        logging.info('--- TEARDOWN --- proxy controller')
        for server in proxy_servers:
            server.remove()

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
        assert found_status == expected_status, "Found validation status " + found_status + " rather than " + \
                                                expected_status + " for validation " + validation_id

    @staticmethod
    def assert_string_length(string, expected_len):
        assert len(string) == expected_len, "Expected len string of: " + str(expected_len) + \
                                            " rather than: " + str(len(string)) + " String value: " + string

    def collect_test_logs(self, cluster, api_client, test: pytest.Function, nodes: Nodes):
        log_dir_name = f"{env_variables['log_folder']}/{test.name}"
        with suppress(ApiException):
            cluster_details = json.loads(json.dumps(cluster.get_details().to_dict(), sort_keys=True, default=str))
            download_logs(api_client, cluster_details, log_dir_name, test.result_call.failed,
                          pull_secret=env_variables.get("pull_secret"))
        self._collect_virsh_logs(nodes, log_dir_name)
        self._collect_journalctl(nodes, log_dir_name)

    @classmethod
    def _collect_virsh_logs(cls, nodes: Nodes, log_dir_name):
        logging.info('Collecting virsh logs\n')
        os.makedirs(log_dir_name, exist_ok=True)
        virsh_log_path = os.path.join(log_dir_name, "libvirt_logs")
        os.makedirs(virsh_log_path, exist_ok=False)

        libvirt_list_path = os.path.join(virsh_log_path, "virsh_list")
        infra_utils.run_command(f"virsh list --all >> {libvirt_list_path}", shell=True)

        libvirt_net_list_path = os.path.join(virsh_log_path, "virsh_net_list")
        infra_utils.run_command(f"virsh net-list --all >> {libvirt_net_list_path}", shell=True)

        network_name = nodes.get_cluster_network()
        virsh_leases_path = os.path.join(virsh_log_path, "net_dhcp_leases")
        infra_utils.run_command(f"virsh net-dhcp-leases {network_name} >> {virsh_leases_path}", shell=True)

        messages_log_path = os.path.join(virsh_log_path, "messages.log")
        shutil.copy('/var/log/messages', messages_log_path)

        qemu_libvirt_path = os.path.join(virsh_log_path, "qemu_libvirt_logs")
        os.makedirs(qemu_libvirt_path, exist_ok=False)
        for node in nodes:
            shutil.copy(f'/var/log/libvirt/qemu/{node.name}.log', f'{qemu_libvirt_path}/{node.name}-qemu.log')

        console_log_path = os.path.join(virsh_log_path, "console_logs")
        os.makedirs(console_log_path, exist_ok=False)
        for node in nodes:
            shutil.copy(f'/var/log/libvirt/qemu/{node.name}-console.log', f'{console_log_path}/{node.name}-console.log')

        libvird_log_path = os.path.join(virsh_log_path, "libvirtd_journal")
        infra_utils.run_command(f"journalctl --since \"{nodes.setup_time}\" "
                                f"-u libvirtd -D /run/log/journal >> {libvird_log_path}", shell=True)

    @staticmethod
    def _collect_journalctl(nodes: Nodes, log_dir_name):
        logging.info('Collecting journalctl\n')
        infra_utils.recreate_folder(log_dir_name, with_chmod=False, force_recreate=False)
        journal_ctl_path = Path(log_dir_name) / 'nodes_journalctl'
        infra_utils.recreate_folder(journal_ctl_path, with_chmod=False)
        for node in nodes:
            try:
                node.run_command(f'sudo journalctl >> /tmp/{node.name}-journalctl')
                journal_path = journal_ctl_path / node.name
                node.download_file(f'/tmp/{node.name}-journalctl', str(journal_path))
            except (RuntimeError, TimeoutError, SSHException):
                logging.info(f'Could not collect journalctl for {node.name}')

    @staticmethod
    def verify_no_logs_uploaded(cluster, cluster_tar_path):
        with pytest.raises(ApiException) as ex:
            cluster.download_installation_logs(cluster_tar_path)
        assert "No log files" in str(ex.value)

    @staticmethod
    def update_oc_config(nodes, cluster):
        os.environ["KUBECONFIG"] = env_variables['kubeconfig_path']
        vips = nodes.controller.get_ingress_and_api_vips()
        api_vip = vips['api_vip']
        infra_utils.config_etc_hosts(cluster_name=cluster.name,
                                     base_dns_domain=env_variables["base_domain"],
                                     api_vip=api_vip)

    def wait_for_controller(self, cluster, nodes):
        cluster.download_kubeconfig_no_ingress()
        self.update_oc_config(nodes, cluster)

        def check_status():
            res = infra_utils.get_assisted_controller_status(env_variables['kubeconfig_path'])
            return "Running" in str(res, 'utf-8')

        waiting.wait(
            lambda: check_status(),
            timeout_seconds=3000,
            sleep_seconds=90,
            waiting_for="controller to be running",
        )

    @pytest.fixture(scope='session')
    def kube_api_client(self):
        yield create_kube_api_client()

    @pytest.fixture()
    def kube_api_context(self, kube_api_client):
        kube_api_context = KubeAPIContext(kube_api_client)

        with kube_api_context:
            yield kube_api_context
