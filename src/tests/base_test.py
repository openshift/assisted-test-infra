import hashlib
import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Type, Union

import libvirt
import pytest
from _pytest.fixtures import FixtureRequest
from assisted_service_client import models
from assisted_service_client.rest import ApiException
from junit_report import JunitFixtureTestCase
from netaddr import IPNetwork
from paramiko import SSHException

import consts
from assisted_test_infra.download_logs.download_logs import download_logs
from assisted_test_infra.test_infra import ClusterName, utils
from assisted_test_infra.test_infra.controllers import (
    AssistedInstallerInfraController,
    IptableRule,
    IPXEController,
    IscsiTargetController,
    LibvirtController,
    NatController,
    Node,
    NodeController,
    NutanixController,
    OciApiController,
    ProxyController,
    RedfishController,
    TangController,
    TerraformController,
    VSphereController,
)
from assisted_test_infra.test_infra.controllers.node_controllers.kvm_s390x_controller import KVMs390xController
from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import collect_virsh_logs
from assisted_test_infra.test_infra.helper_classes import kube_helpers
from assisted_test_infra.test_infra.helper_classes.cluster import Cluster
from assisted_test_infra.test_infra.helper_classes.config import BaseConfig, BaseNodesConfig
from assisted_test_infra.test_infra.helper_classes.day2_cluster import Day2Cluster
from assisted_test_infra.test_infra.helper_classes.events_handler import EventsHandler
from assisted_test_infra.test_infra.helper_classes.infra_env import InfraEnv
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from assisted_test_infra.test_infra.tools import LibvirtNetworkAssets
from service_client import InventoryClient, SuppressAndLog, add_log_record, log
from tests.config import ClusterConfig, InfraEnvConfig, TerraformConfig, global_variables
from tests.config.global_configs import Day2ClusterConfig, NutanixConfig, OciConfig, RedfishConfig, VSphereConfig
from triggers import get_default_triggers
from triggers.env_trigger import Trigger, VariableOrigin


class BaseTest:
    @classmethod
    def _get_parameterized_keys(cls, request: pytest.FixtureRequest) -> List[str]:
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
    def update_parameterized(cls, request: pytest.FixtureRequest, config: BaseConfig) -> None:
        """Update the given configuration object with parameterized values if the key is present"""

        config_type = config.__class__.__name__
        parameterized_keys = cls._get_parameterized_keys(request)

        for fixture_name in parameterized_keys:
            with suppress(pytest.FixtureLookupError, AttributeError):
                if hasattr(config, fixture_name):
                    value = request.getfixturevalue(fixture_name)
                    config.set_value(fixture_name, value, origin=VariableOrigin.PARAMETERIZED)

                    log.debug(f"{config_type}.{fixture_name} value updated from parameterized value to {value}")
                else:
                    raise AttributeError(f"No attribute name {fixture_name} in {config_type} object type")

    @pytest.fixture
    def k8s_assisted_installer_infra_controller(
        self, request: pytest.FixtureRequest
    ) -> AssistedInstallerInfraController:
        """k8 hub cluster wrapper client  object fixture passed to test function
        This function fixture called by testcase, we initialize k8client
        Storing configmap before test begins -> for later restoring
        When test func done, check if configmap was changed and restore config.
        :return:
        """
        log.debug(f"--- SETUP --- Creating k8s_hub cluster for test: {request.node.name}\n")
        hub_cluster_config = AssistedInstallerInfraController(global_variables)
        # before test begins verify all developments are ready
        if not hub_cluster_config.verify_deployments_are_ready():
            assert "k8 hub cluster deployments services not ready/active"

        configmap_before = dict(hub_cluster_config.configmap_data["data"])

        yield hub_cluster_config

        log.debug(f"--- TEARDOWN --- Deleting k8 hub cluster resources for test: {request.node.name}\n")
        configmap_after = dict(hub_cluster_config.configmap_data["data"])
        # Detect if configmap data was changed - need to restore configuration
        hub_cluster_config.rollout_assisted_service(configmap_before, configmap_after, request.node.name)

    @pytest.fixture
    def new_controller_configuration(self, request: FixtureRequest) -> BaseNodesConfig:
        """
        Creates the controller configuration object according to the platform.
        Override this fixture in your test class to provide a custom configuration object
        :rtype: new node controller configuration
        """
        if global_variables.tf_platform == consts.Platforms.VSPHERE:
            config = VSphereConfig()
        elif global_variables.tf_platform == consts.Platforms.NUTANIX:
            config = NutanixConfig()
        elif global_variables.tf_platform == consts.Platforms.OCI:
            config = OciConfig()
        elif global_variables.redfish_enabled:
            config = RedfishConfig()
        else:
            config = TerraformConfig()

        self.update_parameterized(request, config)
        yield config

    @pytest.fixture
    def new_day2_controller_configuration(self, request: FixtureRequest) -> BaseNodesConfig:
        """
        Creates the controller configuration object according to the platform.
        Override this fixture in your test class to provide a custom configuration object
        :rtype: new node controller configuration
        """
        assert global_variables.tf_platform == consts.Platforms.BARE_METAL

        config = TerraformConfig()
        self.update_parameterized(request, config)

        yield config

    @pytest.fixture
    def infraenv_configuration(self) -> InfraEnvConfig:
        yield InfraEnvConfig()

    @pytest.fixture
    def prepared_controller_configuration(self, new_controller_configuration: BaseNodesConfig) -> BaseNodesConfig:
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
    def prepared_day2_controller_configuration(
        self, new_day2_controller_configuration: BaseNodesConfig, day2_cluster_configuration: Day2ClusterConfig
    ) -> BaseNodesConfig:
        assert isinstance(new_day2_controller_configuration, TerraformConfig)

        if day2_cluster_configuration.day2_libvirt_uri:
            # set libvirt_uri in controller configuration
            new_day2_controller_configuration.libvirt_uri = day2_cluster_configuration.day2_libvirt_uri
            day2_base_asset = day2_cluster_configuration.get_base_asset()
            assert all(day2_base_asset.values())  # ensure all values are set

            unique_id = hashlib.sha1(day2_cluster_configuration.day2_libvirt_uri.encode()).hexdigest()
            assets_file = f"{LibvirtNetworkAssets.ASSETS_LOCKFILE_DEFAULT_PATH}/tf_network_pool-{unique_id}.json"
            net_asset = LibvirtNetworkAssets(
                assets_file=assets_file,
                base_asset=day2_base_asset,
                libvirt_uri=day2_cluster_configuration.day2_libvirt_uri,
            )
        else:
            net_asset = LibvirtNetworkAssets()

        # Configuring net asset which currently supported by libvirt terraform only
        new_day2_controller_configuration.net_asset = net_asset.get()

        new_day2_controller_configuration.api_vips = day2_cluster_configuration.day1_cluster_details.api_vips
        new_day2_controller_configuration.ingress_vips = day2_cluster_configuration.day1_cluster_details.ingress_vips
        new_day2_controller_configuration.masters_count = 0
        new_day2_controller_configuration.workers_count = day2_cluster_configuration.day2_workers_count
        new_day2_controller_configuration.masters_count = day2_cluster_configuration.day2_masters_count
        new_day2_controller_configuration.base_cluster_domain = day2_cluster_configuration.day1_base_cluster_domain

        yield new_day2_controller_configuration
        net_asset.release_all()

    @pytest.fixture
    def controller_configuration(
        self, request: pytest.FixtureRequest, prepared_controller_configuration: BaseNodesConfig
    ) -> BaseNodesConfig:
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
    def day2_controller_configuration(
        self, request: pytest.FixtureRequest, prepared_day2_controller_configuration: BaseNodesConfig
    ) -> BaseNodesConfig:
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
        yield utils.run_marked_fixture(
            prepared_day2_controller_configuration, "override_day2_controller_configuration", request
        )

    @pytest.fixture
    def new_cluster_configuration(self, request: FixtureRequest, api_client) -> ClusterConfig:
        """
        Creates new cluster configuration object.
        Override this fixture in your test class to provide a custom cluster configuration. (See TestInstall)
        :rtype: new cluster configuration object
        """
        config = ClusterConfig()
        self.update_parameterized(request, config)

        # Update cluster name before creating the controller if cluster id was provided
        if api_client and config.cluster_id is not None:
            c = api_client.cluster_get(config.cluster_id)
            config.cluster_name = ClusterName(c.name)

        return config

    @pytest.fixture
    def new_day2_cluster_configuration(
        self, request: FixtureRequest, cluster: Cluster, triggers_enabled, triggers
    ) -> Day2ClusterConfig:
        """
        Creates new day2 cluster configuration object.
        Override this fixture in your test class to provide a custom cluster configuration. (See TestInstall)
        :rtype: new day2 cluster configuration object
        """
        config = Day2ClusterConfig()
        self.update_parameterized(request, config)

        if triggers_enabled:
            Trigger.trigger_configurations(
                [config],
                triggers,
            )

        if not cluster.is_installed:
            cluster.prepare_for_installation()
            cluster.start_install_and_wait_for_installed()

        # reference day1 cluster in day2 configuration
        config.day1_cluster = cluster
        config.day1_cluster_details = cluster.get_details()
        config.day1_base_cluster_domain = (
            f"{config.day1_cluster_details.name}.{config.day1_cluster_details.base_dns_domain}"
        )
        config.day1_api_vip_dnsname = f"api.{config.day1_base_cluster_domain}"

        # cluster_id may come already set when CLUSTER_ID environment variable is set
        # we want instead to create a new day2 cluster out of a new or existing day1 cluster
        config.cluster_id = None

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
    def day2_cluster_configuration(
        self, request: pytest.FixtureRequest, new_day2_cluster_configuration: Day2ClusterConfig
    ) -> Day2ClusterConfig:
        yield utils.run_marked_fixture(new_day2_cluster_configuration, "override_day2_cluster_configuration", request)

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
        # Add log record when starting cluster test
        add_log_record(request.node.name)
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
        self,
        triggers_enabled,
        cluster_configuration,
        controller_configuration,
        infra_env_configuration,
        triggers,
    ):
        if triggers_enabled:
            Trigger.trigger_configurations(
                [cluster_configuration, controller_configuration, infra_env_configuration],
                triggers,
            )
        yield

    @pytest.fixture
    def controller(
        self, cluster_configuration: ClusterConfig, controller_configuration: BaseNodesConfig, trigger_configurations
    ) -> NodeController:
        return self.get_node_controller(controller_configuration, cluster_configuration)

    @classmethod
    def get_node_controller(
        cls, controller_configuration: BaseNodesConfig, cluster_configuration: ClusterConfig
    ) -> NodeController:

        platform = (
            global_variables.tf_platform
            if global_variables.tf_platform != cluster_configuration.platform
            else cluster_configuration.platform
        )
        if global_variables.redfish_enabled:
            return RedfishController(controller_configuration, cluster_configuration)

        if platform == consts.Platforms.VSPHERE:
            return VSphereController(controller_configuration, cluster_configuration)

        if platform == consts.Platforms.NUTANIX:
            return NutanixController(controller_configuration, cluster_configuration)

        if platform == consts.Platforms.OCI:
            return OciApiController(controller_configuration, cluster_configuration)

        if platform == consts.CPUArchitecture.S390X:
            return KVMs390xController(controller_configuration, cluster_configuration)

        return TerraformController(controller_configuration, entity_config=cluster_configuration)

    @pytest.fixture
    def day2_controller(
        self, day2_cluster_configuration: Day2ClusterConfig, day2_controller_configuration: BaseNodesConfig
    ) -> NodeController:
        return TerraformController(day2_controller_configuration, entity_config=day2_cluster_configuration)

    @pytest.fixture
    def infraenv_controller(
        self, infra_env_configuration: InfraEnvConfig, controller_configuration: BaseNodesConfig, trigger_configurations
    ) -> NodeController:
        if infra_env_configuration.platform == consts.Platforms.VSPHERE:
            # TODO implement for Vsphere
            raise NotImplementedError

        if infra_env_configuration.platform == consts.Platforms.NUTANIX:
            # TODO implement for Nutanix
            raise NotImplementedError

        return TerraformController(controller_configuration, entity_config=infra_env_configuration)

    @pytest.fixture
    def nodes(self, controller: NodeController) -> Nodes:
        return Nodes(controller)

    @pytest.fixture
    def day2_nodes(self, day2_controller: NodeController) -> Nodes:
        return Nodes(day2_controller)

    @pytest.fixture
    def infraenv_nodes(self, infraenv_controller: NodeController) -> Nodes:
        return Nodes(infraenv_controller)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_nodes(self, nodes: Nodes, cluster_configuration: ClusterConfig) -> Nodes:
        try:
            log.info("--- TEST prepare_nodes  ---")
            yield nodes
        finally:
            if global_variables.test_teardown:
                log.info("--- TEARDOWN --- node controller\n")
                nodes.destroy_all_nodes()
                log.info(f"--- TEARDOWN --- deleting iso file from: {cluster_configuration.iso_download_path}\n")
                Path(cluster_configuration.iso_download_path).unlink(missing_ok=True)
                self.delete_dnsmasq_conf_file(cluster_name=cluster_configuration.cluster_name)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_infraenv_nodes(self, infraenv_nodes: Nodes, infra_env_configuration: InfraEnvConfig) -> Nodes:
        try:
            yield infraenv_nodes
        finally:
            if global_variables.test_teardown:
                log.info("--- TEARDOWN --- node controller\n")
                infraenv_nodes.destroy_all_nodes()
                log.info(f"--- TEARDOWN --- deleting iso file from: {infra_env_configuration.iso_download_path}\n")
                Path(infra_env_configuration.iso_download_path).unlink(missing_ok=True)

    @classmethod
    def _prepare_nodes_network(cls, prepared_nodes: Nodes, controller_configuration: BaseNodesConfig) -> Nodes:
        log.info("--- _prepare_nodes_network\n")
        if (
            (controller_configuration.tf_platform not in (consts.Platforms.BARE_METAL, consts.Platforms.NONE))
            or (hasattr(controller_configuration, "redfish_enabled") and controller_configuration.redfish_enabled)
        ) and (global_variables.cpu_architecture != "s390x"):
            yield prepared_nodes
            log.info("--- _prepare_nodes_network :%s \n", prepared_nodes.get_nodes())
            return

        interfaces = cls.nat_interfaces(controller_configuration)  # todo need to fix mismatch config types
        nat = NatController(interfaces, NatController.get_namespace_index(interfaces[0]))
        nat.add_nat_rules()
        yield prepared_nodes
        cls.teardown_nat(nat)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_nodes_network(self, prepare_nodes: Nodes, controller_configuration: BaseNodesConfig) -> Nodes:
        yield from self._prepare_nodes_network(prepare_nodes, controller_configuration)

    @pytest.fixture
    @JunitFixtureTestCase()
    def prepare_infraenv_nodes_network(
        self, prepare_infraenv_nodes: Nodes, controller_configuration: BaseNodesConfig
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
        ipxe_server: Callable,
        tang_server: Callable,
    ) -> Cluster:
        log.debug(f"--- SETUP --- Creating cluster for test: {request.node.name}\n")
        if cluster_configuration.disk_encryption_mode == consts.DiskEncryptionMode.TANG:
            self._start_tang_server(tang_server, cluster_configuration)

        cluster = Cluster(
            api_client=api_client,
            config=cluster_configuration,
            infra_env_config=infra_env_configuration,
            nodes=prepare_nodes_network,
        )

        assert consts.Platforms.NONE in api_client.get_cluster_supported_platforms(cluster.id)

        if self._does_need_proxy_server(prepare_nodes_network):
            self.__set_up_proxy_server(cluster, cluster_configuration, proxy_server)

        if global_variables.ipxe_boot:
            infra_env = cluster.generate_infra_env()
            ipxe_server_controller = ipxe_server(name="ipxe_controller", api_client=cluster.api_client)
            ipxe_server_controller.run(infra_env_id=infra_env.id, cluster_name=cluster.name)
            cluster_configuration.iso_download_path = utils.get_iso_download_path(
                infra_env_configuration.entity_name.get()
            )

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

    @classmethod
    def _start_tang_server(
        cls, tang_server: Callable, cluster_configuration: ClusterConfig, server_name: str = "tang1"
    ):
        new_tang_server = tang_server(
            name=server_name, port=consts.DEFAULT_TANG_SERVER_PORT, pull_secret=cluster_configuration.pull_secret
        )
        new_tang_server.run()
        new_tang_server.set_thumbprint()
        cluster_configuration.tang_servers = (
            f'[{{"url":"{new_tang_server.address}","thumbprint":"{new_tang_server.thumbprint}"}}]'
        )

    @pytest.fixture
    @JunitFixtureTestCase()
    def day2_cluster(
        self,
        request: FixtureRequest,
        api_client: InventoryClient,
        day2_cluster_configuration: Day2ClusterConfig,
        day2_nodes: Nodes,
    ):
        log.debug(f"--- SETUP --- Creating Day2 cluster for test: {request.node.name}\n")

        day2_cluster = Day2Cluster(
            api_client=api_client,
            config=day2_cluster_configuration,
            infra_env_config=InfraEnvConfig(),
            day2_nodes=day2_nodes,
        )

        yield day2_cluster

        if global_variables.test_teardown:
            with SuppressAndLog(ApiException):
                day2_cluster.deregister_infraenv()

            with suppress(ApiException):
                log.info(f"--- TEARDOWN --- deleting created day2 cluster {day2_cluster.id}\n")
                day2_cluster.delete()

            with suppress(ApiException):
                log.info(f"--- TEARDOWN --- deleting day2 VMs {day2_cluster.id}\n")
                day2_nodes.destroy_all_nodes()

            with suppress(ApiException):
                log.info(f"--- TEARDOWN --- deleting iso file from: {day2_cluster_configuration.iso_download_path}\n")
                Path(day2_cluster_configuration.iso_download_path).unlink(missing_ok=True)

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

    @classmethod
    def nat_interfaces(cls, config: TerraformConfig) -> Tuple[str, str]:
        return config.net_asset.libvirt_network_if, config.net_asset.libvirt_secondary_network_if

    @pytest.fixture
    def configs(self, cluster_configuration, controller_configuration) -> Tuple[ClusterConfig, TerraformConfig]:
        """Get configurations objects - while using configs fixture cluster and tf configs are the same
        For creating new Config object just call it explicitly e.g. ClusterConfig(masters_count=1)"""
        yield cluster_configuration, controller_configuration

    @staticmethod
    def _does_need_proxy_server(nodes: Nodes):
        return nodes is not None and nodes.is_ipv6 and not nodes.is_ipv4

    @staticmethod
    def get_proxy_server(nodes: Nodes, cluster_config: ClusterConfig, proxy_server: Callable) -> ProxyController:
        proxy_name = "squid-" + cluster_config.cluster_name.suffix
        port = utils.scan_for_free_port(consts.DEFAULT_PROXY_SERVER_PORT)

        machine_cidr = nodes.controller.get_primary_machine_cidr()
        host_ip = str(IPNetwork(machine_cidr).ip + 1)
        return proxy_server(name=proxy_name, port=port, host_ip=host_ip, is_ipv6=nodes.is_ipv6)

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
            start_stop_nodes=True,
        ):
            given_nodes = given_nodes or cluster.nodes.nodes
            if start_stop_nodes:
                if cluster.enable_image_download:
                    cluster.generate_and_download_infra_env(iso_download_path=cluster.iso_download_path)
                cluster.nodes.start_given(given_nodes)
                given_node_ips = [node.ips[0] for node in given_nodes]
                cluster.nodes.shutdown_given(given_nodes)
            else:
                given_node_ips = [node.ips[0] for node in given_nodes]

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
    def attach_disk_flags(persistent) -> Callable:
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
    def attach_disk(self) -> Callable:
        yield from self.attach_disk_flags(persistent=False)

    @pytest.fixture(scope="function")
    def attach_disk_persistent(self) -> Callable:
        yield from self.attach_disk_flags(persistent=True)

    @pytest.fixture()
    def attach_interface(self) -> Callable:
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
    def proxy_server(self) -> Callable:
        log.info("--- SETUP --- proxy controller")
        proxy_servers = []

        def start_proxy_server(**kwargs):
            proxy_server = ProxyController(**kwargs)
            proxy_server.run()

            proxy_servers.append(proxy_server)
            return proxy_server

        yield start_proxy_server
        if global_variables.test_teardown:
            log.info("--- TEARDOWN --- proxy controller")
            for server in proxy_servers:
                server.remove()

    @pytest.fixture()
    def tang_server(self) -> Callable:
        log.info("--- SETUP --- Tang controller")
        tang_servers = []

        def start_tang_server(**kwargs):
            tang_server = TangController(**kwargs)
            tang_servers.append(tang_server)

            return tang_server

        yield start_tang_server
        if global_variables.test_teardown:
            log.info("--- TEARDOWN --- Tang controller")
            for server in tang_servers:
                server.remove()

    @pytest.fixture()
    def ipxe_server(self) -> Callable:
        log.info("--- SETUP --- ipxe controller")
        ipxe_server_controllers = []

        def start_ipxe_server(**kwargs):
            ipxe_server_controller = IPXEController(**kwargs)
            ipxe_server_controllers.append(ipxe_server_controller)
            return ipxe_server_controller

        yield start_ipxe_server
        if global_variables.test_teardown:
            log.info("--- TEARDOWN --- ipxe controller")
            for server in ipxe_server_controllers:
                server.remove()

    @pytest.fixture()
    def iscsi_target_controller(self) -> IscsiTargetController:
        log.info("--- SETUP --- iscsi server controller")
        _iscsi_target_controller = IscsiTargetController()

        yield _iscsi_target_controller
        if global_variables.test_teardown:
            log.info("--- TEARDOWN --- iscsi controller")
            _iscsi_target_controller.clean_target()

    @staticmethod
    def assert_http_error_code(api_call: Callable, status: int, reason: str, **kwargs) -> None:
        with pytest.raises(ApiException) as response:
            api_call(**kwargs)
        assert response.value.status == status
        assert response.value.reason == reason

    @staticmethod
    def assert_cluster_validation(
        cluster_info: models.cluster.Cluster, validation_section: str, validation_id: str, expected_status: str
    ) -> None:
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

    def delete_dnsmasq_conf_file(self, cluster_name: str) -> None:
        with SuppressAndLog(FileNotFoundError):
            fname = f"/etc/NetworkManager/dnsmasq.d/openshift-{cluster_name}.conf"
            log.info(f"--- TEARDOWN --- deleting dnsmasq file: {fname}\n")
            os.remove(fname)

    def collect_test_logs(
        self, cluster: Cluster, api_client: InventoryClient, request: pytest.FixtureRequest, nodes: Nodes
    ):
        log_dir_name = f"{global_variables.log_folder}/{request.node.name}"
        with suppress(ApiException, KeyboardInterrupt):
            cluster_details = json.loads(json.dumps(cluster.get_details().to_dict(), sort_keys=True, default=str))
            download_logs(
                api_client,
                cluster_details,
                log_dir_name,
                self._is_test_failed(request),
            )

        if isinstance(nodes.controller, LibvirtController):
            collect_virsh_logs(nodes, log_dir_name)

        self._collect_journalctl(nodes, log_dir_name)

    @classmethod
    def _is_test_failed(cls, test: pytest.FixtureRequest) -> bool:
        # When cancelling a test the test.result_call isn't available, mark it as failed
        return not hasattr(test.node, "result_call") or test.node.result_call.failed

    @staticmethod
    def _collect_journalctl(nodes: Nodes, log_dir_name: str) -> None:
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
    def update_oc_config(nodes: Nodes, cluster: Cluster) -> None:
        os.environ["KUBECONFIG"] = cluster.kubeconfig_path
        if nodes.nodes_count == 1:
            try:
                # Bubble up exception when vip not found for sno, returns ip string
                ip_vip = cluster.get_ip_for_single_node(
                    cluster.api_client, cluster.id, cluster.get_primary_machine_cidr()
                )
            except Exception as e:
                log.warning(f"ip_vip for single node not found for {cluster.name}: {str(e)}")
                ip_vip = ""
            api_vips = [{"ip": ip_vip}]
        else:
            try:
                # Bubble up exception when vip not found for multiple nodes
                api_vips = nodes.controller.get_ingress_and_api_vips()["api_vips"]
            except Exception as e:
                log.warning(f"api_vips for multi node not found for {cluster.name}: {str(e)}")
                api_vips = [{"ip": ""}]

        api_vip_address = api_vips[0].get("ip", "") if len(api_vips) > 0 else ""

        utils.config_etc_hosts(
            cluster_name=cluster.name, base_dns_domain=global_variables.base_dns_domain, api_vip=api_vip_address
        )
