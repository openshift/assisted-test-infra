import json
import os
import shutil
from contextlib import suppress
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Type, Union

import libvirt
import pytest
import waiting
from _pytest.fixtures import FixtureRequest
from assisted_service_client import models
from assisted_service_client.rest import ApiException
from junit_report import JunitFixtureTestCase, JunitTestCase
from netaddr import IPNetwork
from paramiko import SSHException

import consts
from assisted_test_infra.download_logs.download_logs import download_logs
from assisted_test_infra.test_infra import BaseTerraformConfig, Nodes, utils
from assisted_test_infra.test_infra.controllers import (
    IptableRule,
    NatController,
    Node,
    NodeController,
    ProxyController,
    TerraformController,
    VSphereController,
)
from assisted_test_infra.test_infra.helper_classes import kube_helpers
from assisted_test_infra.test_infra.helper_classes.cluster import Cluster
from assisted_test_infra.test_infra.helper_classes.config import BaseConfig, BaseNodeConfig
from assisted_test_infra.test_infra.helper_classes.day2_cluster import Day2Cluster
from assisted_test_infra.test_infra.helper_classes.events_handler import EventsHandler
from assisted_test_infra.test_infra.helper_classes.infra_env import InfraEnv
from assisted_test_infra.test_infra.tools import LibvirtNetworkAssets
from service_client import InventoryClient, SuppressAndLog, log
from tests.config import ClusterConfig, InfraEnvConfig, TerraformConfig, global_variables
from tests.config.global_configs import Day2ClusterConfig, VSphereConfig
from triggers import get_default_triggers
from triggers.env_trigger import Trigger


class BaseTest:
    @classmethod
    def _get_parameterized_keys(cls, request: pytest.FixtureRequest):
        """This method return the parameterized keys decorated the current test function.
        If the key is a tuple (e.g. 'ipv4, ipv6') is will return them both as individuals"""

        parameterized_keys = []
        optional_keys = [m.args[0] for m in request.keywords.node.own_markers if m and m.name == "parametrize"]

        for key in optional_keys:
            keys = key.split(",")
            for k in keys:
                parameterized_keys.append(k.strip())

        return parameterized_keys

    @classmethod
    def update_parameterized(cls, request: pytest.FixtureRequest, config: BaseConfig):
        """Update the given configuration object with parameterized values if the key is present"""

        config_type = config.__class__.__name__
        parameterized_keys = cls._get_parameterized_keys(request)

        for fixture_name in parameterized_keys:
            with suppress(pytest.FixtureLookupError, AttributeError):
                if hasattr(config, fixture_name):
                    value = request.getfixturevalue(fixture_name)
                    config.set_value(fixture_name, value)

                    log.debug(f"{config_type}.{fixture_name} value updated from parameterized value to {value}")
                else:
                    raise AttributeError(f"No attribute name {fixture_name} in {config_type} object type")

    @pytest.fixture
    def new_controller_configuration(self, request: FixtureRequest) -> BaseNodeConfig:
        """
        Creates the controller configuration object according to the platform.
        Override this fixture in your test class to provide a custom configuration object
        :rtype: new node controller configuration
        """
        if global_variables.platform == consts.Platforms.VSPHERE:
            config = VSphereConfig()
        else:
            config = TerraformConfig()

        self.update_parameterized(request, config)
        yield config

    @pytest.fixture
    def infraenv_configuration(self) -> InfraEnvConfig:
        yield InfraEnvConfig()

    @pytest.fixture
    def day2_cluster_configuration(self) -> Day2ClusterConfig:
        yield Day2ClusterConfig()

    @pytest.fixture
    def prepared_controller_configuration(self, new_controller_configuration: BaseNodeConfig) -> BaseNodeConfig:
        if not isinstance(new_controller_configuration, TerraformConfig):
            yield new_controller_configuration
            return

        # Configuring net asset which currently supported by libvirt terraform only
        net_asset = LibvirtNetworkAssets()
        new_controller_configuration.net_asset = net_asset.get()

        if new_controller_configuration.bootstrap_in_place:
            new_controller_configuration.single_node_ip = new_controller_configuration.net_asset.machine_cidr.replace(
                "0/24", "10"
            )

        yield new_controller_configuration
        net_asset.release_all()

    @pytest.fixture
    def controller_configuration(
        self, request: pytest.FixtureRequest, prepared_controller_configuration: BaseNodeConfig
    ) -> BaseNodeConfig:
        """
        Allows the test to modify the controller configuration by registering a custom fixture.
        To register the custom fixture you have to mark the test with "override_controller_configuration" marker.

        For example:

        @pytest.fixture
        def FIXTURE_NAME(self, prepared_controller_configuration):
            yield prepared_controller_configuration

        @pytest.mark.override_controller_configuration(FIXTURE_NAME.__name__)
        def test_something(cluster):
            pass
        """
        yield utils.run_marked_fixture(prepared_controller_configuration, "override_controller_configuration", request)

    @pytest.fixture
    def new_cluster_configuration(self, request: FixtureRequest) -> ClusterConfig:
        """
        Creates new cluster configuration object.
        Override this fixture in your test class to provide a custom cluster configuration. (See TestInstall)
        :rtype: new cluster configuration object
        """
        config = ClusterConfig()
        self.update_parameterized(request, config)

        return config

    @pytest.fixture
    def new_infra_env_configuration(self, request: FixtureRequest) -> InfraEnvConfig:
        """
        Creates new infra-env configuration object.
        Override this fixture in your test class to provide a custom cluster configuration. (See TestInstall)
        :rtype: new cluster configuration object
        """
        config = InfraEnvConfig()
        self.update_parameterized(request, config)

        return config

    @pytest.fixture
    def cluster_configuration(
        self, request: pytest.FixtureRequest, new_cluster_configuration: ClusterConfig
    ) -> ClusterConfig:
        """
        Allows the test to modify the cluster configuration by registering a custom fixture.
        To register the custom fixture you have to mark the test with "override_cluster_configuration" marker.

        For example:

        @pytest.fixture
        def FIXTURE_NAME(self, new_cluster_configuration):
            yield new_cluster_configuration

        @pytest.mark.override_cluster_configuration(FIXTURE_NAME.__name__)
        def test_something(cluster):
            pass
        """
        yield utils.run_marked_fixture(new_cluster_configuration, "override_cluster_configuration", request)

    @pytest.fixture
    def infra_env_configuration(
        self, request: pytest.FixtureRequest, new_infra_env_configuration: InfraEnvConfig
    ) -> InfraEnvConfig:
        """
        Allows the test to modify the infra-env configuration by registering a custom fixture.
        To register the custom fixture you have to mark the test with "override_infra_env_configuration" marker.

        For example:

        @pytest.fixture
        def FIXTURE_NAME(self, new_infra_env_configuration):
            yield new_infra_env_configuration

        @pytest.mark.override_infra_env_configuration(FIXTURE_NAME.__name__)
        def test_something(cluster):
            pass
        """
        yield utils.run_marked_fixture(new_infra_env_configuration, "override_infra_env_configuration", request)

    @pytest.fixture
    def triggers_enabled(self) -> bool:
        """Can be override for disabling the triggers"""
        return True

    @pytest.fixture
    def triggers(self) -> Dict[str, Trigger]:
        return get_default_triggers()

    @pytest.fixture
    def trigger_configurations(
        self, triggers_enabled, cluster_configuration, controller_configuration, infra_env_configuration, triggers
    ):

        if triggers_enabled:
            Trigger.trigger_configurations(
                [cluster_configuration, controller_configuration, infra_env_configuration], triggers
            )
        yield cluster_configuration, controller_configuration, infra_env_configuration

    @pytest.fixture
    def controller(
        self, cluster_configuration: ClusterConfig, controller_configuration: BaseNodeConfig, trigger_configurations
    ) -> NodeController:

        if cluster_configuration.platform == consts.Platforms.VSPHERE:
            return VSphereController(controller_configuration, cluster_configuration)

        return TerraformController(controller_configuration, entity_config=cluster_configuration)

    @pytest.fixture
    def infraenv_controller(
        self, infra_env_configuration: InfraEnvConfig, controller_configuration: BaseNodeConfig, trigger_configurations
    ) -> NodeController:
        if infra_env_configuration.platform == consts.Platforms.VSPHERE:
            # TODO implement for Vsphere
            raise NotImplementedError

        return TerraformController(controller_configuration, entity_config=infra_env_configuration)

    @pytest.fixture
    def nodes(self, controller: NodeController) -> Nodes:
        return Nodes(controller)

    @pytest.fixture
    def infraenv_nodes(self, infraenv_controller: NodeController) -> Nodes:
        return Nodes(infraenv_controller)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_nodes(self, nodes: Nodes, cluster_configuration: ClusterConfig) -> Nodes:
        try:
            nodes.prepare_nodes()
            yield nodes
        finally:
            if global_variables.test_teardown:
                log.info("--- TEARDOWN --- node controller\n")
                nodes.destroy_all_nodes()
                log.info(f"--- TEARDOWN --- deleting iso file from: {cluster_configuration.iso_download_path}\n")
                utils.run_command(f"rm -f {cluster_configuration.iso_download_path}", shell=True)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_infraenv_nodes(self, infraenv_nodes: Nodes, infra_env_configuration: InfraEnvConfig) -> Nodes:
        try:
            infraenv_nodes.prepare_nodes()
            yield infraenv_nodes
        finally:
            if global_variables.test_teardown:
                log.info("--- TEARDOWN --- node controller\n")
                infraenv_nodes.destroy_all_nodes()
                log.info(f"--- TEARDOWN --- deleting iso file from: {infra_env_configuration.iso_download_path}\n")
                utils.run_command(f"rm -f {infra_env_configuration.iso_download_path}", shell=True)

    @classmethod
    def _prepare_nodes_network(cls, prepared_nodes: Nodes, controller_configuration: BaseNodeConfig) -> Nodes:
        if global_variables.platform not in (consts.Platforms.BARE_METAL, consts.Platforms.NONE):
            yield prepared_nodes
            return

        interfaces = cls.nat_interfaces(controller_configuration)  # todo need to fix mismatch config types
        nat = NatController(interfaces, NatController.get_namespace_index(interfaces[0]))
        nat.add_nat_rules()
        yield prepared_nodes
        cls.teardown_nat(nat)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_nodes_network(self, prepare_nodes: Nodes, controller_configuration: BaseNodeConfig) -> Nodes:
        yield from self._prepare_nodes_network(prepare_nodes, controller_configuration)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_infraenv_nodes_network(
        self, prepare_infraenv_nodes: Nodes, controller_configuration: BaseNodeConfig
    ) -> Nodes:
        yield from self._prepare_nodes_network(prepare_infraenv_nodes, controller_configuration)

    @staticmethod
    def teardown_nat(nat: NatController) -> None:
        if global_variables.test_teardown and nat:
            nat.remove_nat_rules()

    @pytest.fixture
    def events_handler(self, api_client: InventoryClient) -> EventsHandler:
        yield EventsHandler(api_client)

    @pytest.fixture
    @JunitFixtureTestCase()
    def cluster(
        self,
        api_client: InventoryClient,
        request: FixtureRequest,
        infra_env_configuration: InfraEnvConfig,
        proxy_server,
        prepare_nodes_network: Nodes,
        cluster_configuration: ClusterConfig,
    ):
        log.debug(f"--- SETUP --- Creating cluster for test: {request.node.name}\n")
        cluster = Cluster(
            api_client=api_client,
            config=cluster_configuration,
            infra_env_config=infra_env_configuration,
            nodes=prepare_nodes_network,
        )

        if self._does_need_proxy_server(prepare_nodes_network):
            self.__set_up_proxy_server(cluster, cluster_configuration, proxy_server)

        yield cluster

        if self._is_test_failed(request):
            log.info(f"--- TEARDOWN --- Collecting Logs for test: {request.node.name}\n")
            self.collect_test_logs(cluster, api_client, request, cluster.nodes)

            if global_variables.test_teardown:
                if cluster.is_installing() or cluster.is_finalizing():
                    cluster.cancel_install()

        if global_variables.test_teardown:
            with SuppressAndLog(ApiException):
                cluster.deregister_infraenv()

            with suppress(ApiException):
                log.info(f"--- TEARDOWN --- deleting created cluster {cluster.id}\n")
                cluster.delete()

    @pytest.fixture
    @JunitFixtureTestCase()
    def day2_cluster(
        self,
        api_client: InventoryClient,
        request: FixtureRequest,
        day2_cluster_configuration: Day2ClusterConfig,
    ):
        log.debug(f"--- SETUP --- Creating Day2 cluster for test: {request.node.name}\n")
        cluster = Day2Cluster(
            api_client=api_client,
            config=day2_cluster_configuration,
        )

        yield cluster

    @pytest.fixture
    @JunitFixtureTestCase()
    def infra_env(
        self,
        api_client: InventoryClient,
        request: FixtureRequest,
        proxy_server,
        prepare_infraenv_nodes_network: Nodes,
        infra_env_configuration: InfraEnvConfig,
    ):
        log.debug(f"--- SETUP --- Creating InfraEnv for test: {request.node.name}\n")
        infra_env = InfraEnv(
            api_client=api_client, config=infra_env_configuration, nodes=prepare_infraenv_nodes_network
        )

        yield infra_env
        log.info("--- TEARDOWN --- Infra env\n")

        if global_variables.test_teardown:
            with SuppressAndLog(ApiException):
                infra_env.deregister()

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepared_cluster(self, cluster):
        cluster.prepare_for_installation()
        yield cluster

    @pytest.fixture(scope="function")
    def get_nodes(self) -> Callable[[BaseTerraformConfig, ClusterConfig], Nodes]:
        """Currently support only single instance of nodes"""
        nodes_data = dict()

        @JunitTestCase()
        def get_nodes_func(tf_config: BaseTerraformConfig, cluster_config: ClusterConfig):
            if "nodes" in nodes_data:
                return nodes_data["nodes"]

            nodes_data["configs"] = cluster_config, tf_config

            net_asset = LibvirtNetworkAssets()
            tf_config.net_asset = net_asset.get()
            nodes_data["net_asset"] = net_asset

            controller = TerraformController(tf_config, entity_config=cluster_config)
            nodes = Nodes(controller)
            nodes_data["nodes"] = nodes

            nodes.prepare_nodes()

            interfaces = self.nat_interfaces(tf_config)
            nat = NatController(interfaces, NatController.get_namespace_index(interfaces[0]))
            nat.add_nat_rules()

            nodes_data["nat"] = nat

            return nodes

        yield get_nodes_func

        _nodes: Nodes = nodes_data.get("nodes")
        _cluster_config, _tf_config = nodes_data.get("configs", (None, None))
        _nat: NatController = nodes_data.get("nat")
        _net_asset: LibvirtNetworkAssets = nodes_data.get("net_asset")

        try:
            if _nodes and global_variables.test_teardown:
                log.info("--- TEARDOWN --- node controller\n")
                _nodes.destroy_all_nodes()
                log.info(f"--- TEARDOWN --- deleting iso file from: {_cluster_config.iso_download_path}\n")
                utils.run_command(f"rm -f {_cluster_config.iso_download_path}", shell=True)
                self.teardown_nat(_nat)

        finally:
            if _net_asset:
                _net_asset.release_all()

    @pytest.fixture(scope="function")
    def get_nodes_infraenv(self) -> Callable[[BaseTerraformConfig, InfraEnvConfig], Nodes]:
        """Currently support only single instance of nodes"""
        nodes_data = dict()

        @JunitTestCase()
        def get_nodes_func(tf_config: BaseTerraformConfig, infraenv_config: InfraEnvConfig):
            if "nodes" in nodes_data:
                return nodes_data["nodes"]

            nodes_data["configs"] = infraenv_config, tf_config

            net_asset = LibvirtNetworkAssets()
            tf_config.net_asset = net_asset.get()
            nodes_data["net_asset"] = net_asset

            controller = TerraformController(tf_config, entity_config=infraenv_config)
            nodes = Nodes(controller)
            nodes_data["nodes"] = nodes

            nodes.prepare_nodes()

            interfaces = self.nat_interfaces(tf_config)
            nat = NatController(interfaces, NatController.get_namespace_index(interfaces[0]))
            nat.add_nat_rules()

            nodes_data["nat"] = nat

            return nodes

        yield get_nodes_func

        _nodes: Nodes = nodes_data.get("nodes")
        _infraenv_config, _tf_config = nodes_data.get("configs")
        _nat: NatController = nodes_data.get("nat")
        _net_asset: LibvirtNetworkAssets = nodes_data.get("net_asset")

        try:
            if _nodes and global_variables.test_teardown:
                log.info("--- TEARDOWN --- node controller\n")
                _nodes.destroy_all_nodes()
                log.info(f"--- TEARDOWN --- deleting iso file from: {_infraenv_config.iso_download_path}\n")
                utils.run_command(f"rm -f {_infraenv_config.iso_download_path}", shell=True)
                self.teardown_nat(_nat)

        finally:
            if _net_asset:
                _net_asset.release_all()

    @classmethod
    def nat_interfaces(cls, config: TerraformConfig) -> Tuple[str, str]:
        return config.net_asset.libvirt_network_if, config.net_asset.libvirt_secondary_network_if

    @pytest.fixture()
    @JunitFixtureTestCase()
    def get_cluster(
        self, api_client, request, proxy_server, get_nodes, infra_env_configuration
    ) -> Callable[[Nodes, ClusterConfig], Cluster]:
        """Do not use get_nodes fixture in this fixture. It's here only to force pytest teardown
        nodes after cluster"""

        clusters = list()

        @JunitTestCase()
        def get_cluster_func(nodes: Nodes, cluster_config: ClusterConfig) -> Cluster:
            log.debug(f"--- SETUP --- Creating cluster for test: {request.node.name}\n")
            _cluster = Cluster(
                api_client=api_client, config=cluster_config, nodes=nodes, infra_env_config=infra_env_configuration
            )

            if self._does_need_proxy_server(nodes):
                self.__set_up_proxy_server(_cluster, cluster_config, proxy_server)

            clusters.append(_cluster)
            return _cluster

        yield get_cluster_func
        for cluster in clusters:
            if self._is_test_failed(request):
                log.info(f"--- TEARDOWN --- Collecting Logs for test: {request.node.name}\n")
                self.collect_test_logs(cluster, api_client, request, cluster.nodes)
            if global_variables.test_teardown:
                if cluster.id and (cluster.is_installing() or cluster.is_finalizing()):
                    cluster.cancel_install()

                with suppress(ApiException):
                    log.info(f"--- TEARDOWN --- deleting created cluster {cluster.id}\n")
                    cluster.delete()

    @pytest.fixture
    def configs(self, cluster_configuration, controller_configuration) -> Tuple[ClusterConfig, TerraformConfig]:
        """Get configurations objects - while using configs fixture cluster and tf configs are the same
        For creating new Config object just call it explicitly e.g. ClusterConfig(masters_count=1)"""
        yield cluster_configuration, controller_configuration

    @staticmethod
    def _does_need_proxy_server(nodes: Nodes):
        return nodes and nodes.is_ipv6 and not nodes.is_ipv4

    @staticmethod
    def get_proxy_server(nodes: Nodes, cluster_config: ClusterConfig, proxy_server: Callable) -> ProxyController:
        proxy_name = "squid-" + cluster_config.cluster_name.suffix
        port = utils.scan_for_free_port(consts.DEFAULT_PROXY_SERVER_PORT)

        machine_cidr = nodes.controller.get_primary_machine_cidr()
        host_ip = str(IPNetwork(machine_cidr).ip + 1)
        return proxy_server(name=proxy_name, port=port, dir=proxy_name, host_ip=host_ip, is_ipv6=nodes.is_ipv6)

    @classmethod
    def get_proxy(
        cls,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        proxy_server: Callable,
        proxy_generator: Union[Type[models.Proxy], Type[kube_helpers.Proxy]],
    ) -> Union[models.Proxy, kube_helpers.Proxy]:
        """Get proxy configurations for kubeapi and for restapi. proxy_generator need to be with the
        following signature: Proxy(http_proxy=<value1>, https_proxy=<value2>, no_proxy=<value3>)"""

        proxy_server = cls.get_proxy_server(nodes, cluster_config, proxy_server)
        machine_cidr = nodes.controller.get_primary_machine_cidr()

        no_proxy = []
        no_proxy += [str(cluster_network.cidr) for cluster_network in cluster_config.cluster_networks]
        no_proxy += [str(service_network.cidr) for service_network in cluster_config.service_networks]
        no_proxy += [machine_cidr]
        no_proxy += [f".{str(cluster_config.cluster_name)}.redhat.com"]
        no_proxy = ",".join(no_proxy)

        return proxy_generator(http_proxy=proxy_server.address, https_proxy=proxy_server.address, no_proxy=no_proxy)

    @classmethod
    def __set_up_proxy_server(cls, cluster: Cluster, cluster_config: ClusterConfig, proxy_server):
        proxy = cls.get_proxy(cluster.nodes, cluster_config, proxy_server, models.Proxy)

        cluster.set_proxy_values(proxy_values=proxy)
        install_config = cluster.get_install_config()
        proxy_details = install_config.get("proxy") or install_config.get("Proxy")
        assert proxy_details, str(install_config)
        assert (
            proxy_details.get("httpsProxy") == proxy.https_proxy
        ), f"{proxy_details.get('httpsProxy')} should equal {proxy.https_proxy}"

    @pytest.fixture()
    def iptables(self) -> Callable[[Cluster, List[IptableRule], Optional[List[Node]]], None]:
        rules = []

        def set_iptables_rules_for_nodes(
            cluster: Cluster,
            iptables_rules: List[IptableRule],
            given_nodes=None,
        ):
            given_node_ips = []
            given_nodes = given_nodes or cluster.nodes.nodes

            if cluster.enable_image_download:
                cluster.generate_and_download_infra_env(iso_download_path=cluster.iso_download_path)
            cluster.nodes.start_given(given_nodes)
            for node in given_nodes:
                given_node_ips.append(node.ips[0])
            cluster.nodes.shutdown_given(given_nodes)

            log.info(f"Given node ips: {given_node_ips}")

            for _rule in iptables_rules:
                _rule.add_sources(given_node_ips)
                rules.append(_rule)
                _rule.insert()

        yield set_iptables_rules_for_nodes
        log.info("---TEARDOWN iptables ---")
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
        if global_variables.test_teardown:
            for modified_node in modified_nodes:
                try:
                    modified_node.detach_all_test_disks()
                    log.info(f"Successfully detach test disks from node {modified_node.name}")
                except (libvirt.libvirtError, FileNotFoundError):
                    log.warning(f"Failed to detach test disks from node {modified_node.name}")

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
            log.info(f"Deleting custom networks:{added_networks}")
            with suppress(Exception):
                node_obj = added_network.get("node")
                node_obj.undefine_interface(added_network.get("mac"))
                node_obj.destroy_network(added_network.get("network"))

    @pytest.fixture()
    def proxy_server(self):
        log.info("--- SETUP --- proxy controller")
        proxy_servers = []

        def start_proxy_server(**kwargs):
            proxy_server = ProxyController(**kwargs)
            proxy_servers.append(proxy_server)

            return proxy_server

        yield start_proxy_server
        if global_variables.test_teardown:
            log.info("--- TEARDOWN --- proxy controller")
            for server in proxy_servers:
                server.remove()

    @staticmethod
    def get_cluster_by_name(api_client, cluster_name):
        clusters = api_client.clusters_list()
        for cluster in clusters:
            if cluster["name"] == cluster_name:
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
        found_status = utils.get_cluster_validation_value(cluster_info, validation_section, validation_id)
        assert found_status == expected_status, (
            "Found validation status "
            + found_status
            + " rather than "
            + expected_status
            + " for validation "
            + validation_id
        )

    @staticmethod
    def assert_string_length(string, expected_len):
        assert len(string) == expected_len, (
            "Expected len string of: "
            + str(expected_len)
            + " rather than: "
            + str(len(string))
            + " String value: "
            + string
        )

    def collect_test_logs(self, cluster, api_client, request, nodes: Nodes):
        log_dir_name = f"{global_variables.log_folder}/{request.node.name}"
        with suppress(ApiException):
            cluster_details = json.loads(json.dumps(cluster.get_details().to_dict(), sort_keys=True, default=str))
            download_logs(
                api_client,
                cluster_details,
                log_dir_name,
                self._is_test_failed(request),
                pull_secret=global_variables.pull_secret,
            )
        self._collect_virsh_logs(nodes, log_dir_name)
        self._collect_journalctl(nodes, log_dir_name)

    @classmethod
    def _is_test_failed(cls, test):
        # When cancelling a test the test.result_call isn't available, mark it as failed
        return not hasattr(test.node, "result_call") or test.node.result_call.failed

    @classmethod
    def _collect_virsh_logs(cls, nodes: Nodes, log_dir_name):
        log.info("Collecting virsh logs\n")
        os.makedirs(log_dir_name, exist_ok=True)
        virsh_log_path = os.path.join(log_dir_name, "libvirt_logs")
        os.makedirs(virsh_log_path, exist_ok=False)

        libvirt_list_path = os.path.join(virsh_log_path, "virsh_list")
        utils.run_command(f"virsh list --all >> {libvirt_list_path}", shell=True)

        libvirt_net_list_path = os.path.join(virsh_log_path, "virsh_net_list")
        utils.run_command(f"virsh net-list --all >> {libvirt_net_list_path}", shell=True)

        network_name = nodes.get_cluster_network()
        virsh_leases_path = os.path.join(virsh_log_path, "net_dhcp_leases")
        utils.run_command(f"virsh net-dhcp-leases {network_name} >> {virsh_leases_path}", shell=True)

        messages_log_path = os.path.join(virsh_log_path, "messages.log")
        try:
            shutil.copy("/var/log/messages", messages_log_path)
        except FileNotFoundError:
            log.warning("Failed to copy /var/log/messages, file does not exist")

        qemu_libvirt_path = os.path.join(virsh_log_path, "qemu_libvirt_logs")
        os.makedirs(qemu_libvirt_path, exist_ok=False)
        for node in nodes:
            try:
                shutil.copy(f"/var/log/libvirt/qemu/{node.name}.log", f"{qemu_libvirt_path}/{node.name}-qemu.log")
            except FileNotFoundError:
                log.warning(f"Failed to copy {node.name} qemu log, file does not exist")

        console_log_path = os.path.join(virsh_log_path, "console_logs")
        os.makedirs(console_log_path, exist_ok=False)
        for node in nodes:
            try:
                shutil.copy(
                    f"/var/log/libvirt/qemu/{node.name}-console.log", f"{console_log_path}/{node.name}-console.log"
                )
            except FileNotFoundError:
                log.warning(f"Failed to copy {node.name} console log, file does not exist")

        libvird_log_path = os.path.join(virsh_log_path, "libvirtd_journal")
        utils.run_command(
            f'journalctl --since "{nodes.setup_time}" ' f"-u libvirtd -D /run/log/journal >> {libvird_log_path}",
            shell=True,
        )

    @staticmethod
    def _collect_journalctl(nodes: Nodes, log_dir_name):
        log.info("Collecting journalctl\n")
        utils.recreate_folder(log_dir_name, with_chmod=False, force_recreate=False)
        journal_ctl_path = Path(log_dir_name) / "nodes_journalctl"
        utils.recreate_folder(journal_ctl_path, with_chmod=False)
        for node in nodes:
            try:
                node.run_command(f"sudo journalctl >> /tmp/{node.name}-journalctl")
                journal_path = journal_ctl_path / node.name
                node.download_file(f"/tmp/{node.name}-journalctl", str(journal_path))
            except (RuntimeError, TimeoutError, SSHException):
                log.info(f"Could not collect journalctl for {node.name}")

    @staticmethod
    def verify_no_logs_uploaded(cluster, cluster_tar_path):
        with pytest.raises(ApiException) as ex:
            cluster.download_installation_logs(cluster_tar_path)
        assert "No log files" in str(ex.value)

    @staticmethod
    def update_oc_config(nodes, cluster):
        os.environ["KUBECONFIG"] = cluster.kubeconfig_path
        if nodes.masters_count == 1:
            main_cidr = cluster.get_primary_machine_cidr()
            api_vip = cluster.get_ip_for_single_node(cluster.api_client, cluster.id, main_cidr)
        else:
            vips = nodes.controller.get_ingress_and_api_vips()
            api_vip = vips["api_vip"]
        utils.config_etc_hosts(
            cluster_name=cluster.name, base_dns_domain=global_variables.base_dns_domain, api_vip=api_vip
        )

    def wait_for_controller(self, cluster, nodes):
        cluster.download_kubeconfig_no_ingress()
        self.update_oc_config(nodes, cluster)

        def check_status():
            res = utils.get_assisted_controller_status(cluster.kubeconfig_path)
            return "Running" in str(res, "utf-8")

        waiting.wait(
            lambda: check_status(),
            timeout_seconds=900,
            sleep_seconds=30,
            waiting_for="controller to be running",
        )
