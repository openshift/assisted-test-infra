import base64
import json
import os
import tempfile
from typing import Callable, List, Optional

import openshift as oc
import pytest
import waiting
from junit_report import JunitFixtureTestCase, JunitTestCase, JunitTestSuite
from waiting import TimeoutExpired

from assisted_test_infra.download_logs import collect_debug_info_from_cluster
from assisted_test_infra.test_infra import Nodes, utils
from assisted_test_infra.test_infra.helper_classes.config import BaseNodeConfig
from assisted_test_infra.test_infra.helper_classes.hypershift import HyperShift
from assisted_test_infra.test_infra.helper_classes.kube_helpers import (
    Agent,
    AgentClusterInstall,
    ClusterDeployment,
    InfraEnv,
    KubeAPIContext,
    Proxy,
    Secret,
)
from assisted_test_infra.test_infra.utils.kubeapi_utils import get_ip_for_single_node
from service_client import log
from tests.base_kubeapi_test import BaseKubeAPI
from tests.config import ClusterConfig, InfraEnvConfig, global_variables


class TestKubeAPI(BaseKubeAPI):
    KUBEAPI_IP_OPTIONS = [(False, True), (True, False)]

    @pytest.fixture
    def sno_controller_configuration(self, prepared_controller_configuration: BaseNodeConfig) -> BaseNodeConfig:
        self._configure_single_node(prepared_controller_configuration)
        yield prepared_controller_configuration

    @pytest.fixture
    def highly_available_controller_configuration(self, prepared_controller_configuration: BaseNodeConfig):
        self._configure_highly_available(prepared_controller_configuration)
        yield prepared_controller_configuration

    @pytest.mark.kube_api
    @JunitTestSuite()
    @pytest.mark.parametrize("is_ipv4, is_ipv6", utils.get_kubeapi_protocol_options())
    @pytest.mark.override_controller_configuration(sno_controller_configuration.__name__)
    def test_kubeapi(
        self,
        cluster_configuration: ClusterConfig,
        kube_api_context: KubeAPIContext,
        proxy_server: Callable,
        prepare_nodes_network: Nodes,
        is_ipv4: bool,
        is_ipv6: bool,
    ):
        self.kube_api_test(
            kube_api_context,
            prepare_nodes_network,
            cluster_configuration,
            proxy_server if cluster_configuration.is_ipv6 else None,
        )

    @JunitTestSuite()
    @pytest.mark.kube_api
    @pytest.mark.override_controller_configuration(highly_available_controller_configuration.__name__)
    def test_capi_provider(self, cluster_configuration, kube_api_context, prepare_nodes_network):
        self.capi_test(kube_api_context, prepare_nodes_network, cluster_configuration)

    @JunitTestCase()
    def kube_api_test(
        self,
        kube_api_context: KubeAPIContext,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        proxy_server: Optional[Callable] = None,
        *,
        is_disconnected: bool = False,
    ):
        cluster_name = cluster_config.cluster_name.get()
        api_client = kube_api_context.api_client
        spoke_namespace = kube_api_context.spoke_namespace

        # TODO resolve it from the service if the node controller doesn't have this information
        #  (please see cluster.get_primary_machine_cidr())
        machine_cidr = nodes.controller.get_primary_machine_cidr()

        agent_cluster_install = AgentClusterInstall(
            api_client, f"{cluster_name}-agent-cluster-install", spoke_namespace
        )

        secret = Secret(api_client, f"{cluster_name}-secret", spoke_namespace)
        secret.create(pull_secret=cluster_config.pull_secret)

        cluster_deployment = ClusterDeployment(api_client, cluster_name, spoke_namespace)
        cluster_deployment.create(agent_cluster_install_ref=agent_cluster_install.ref, secret=secret)

        proxy = self.setup_proxy(nodes, cluster_config, proxy_server)
        agent_cluster_install.create(
            cluster_deployment_ref=cluster_deployment.ref,
            image_set_ref=self.deploy_image_set(cluster_name, api_client),
            cluster_cidr=cluster_config.cluster_networks[0].cidr,
            host_prefix=cluster_config.cluster_networks[0].host_prefix,
            service_network=cluster_config.service_networks[0].cidr,
            ssh_pub_key=cluster_config.ssh_public_key,
            hyperthreading=cluster_config.hyperthreading,
            control_plane_agents=nodes.masters_count,
            worker_agents=nodes.workers_count,
            machine_cidr=machine_cidr,
            proxy=proxy.as_dict() if proxy else {},
        )
        agent_cluster_install.wait_to_be_ready(ready=False)

        if cluster_config.is_static_ip:
            self.apply_static_network_config(kube_api_context, nodes, cluster_name)

        if is_disconnected:
            log.info("getting igntion and install config override for disconected install")
            ca_bundle = self.get_ca_bundle_from_hub(spoke_namespace)
            self.patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle)
            ignition_config_override = self.get_ignition_config_override(ca_bundle)
        else:
            ignition_config_override = None

        infra_env = InfraEnv(api_client, f"{cluster_name}-infra-env", spoke_namespace)
        infra_env.create(
            cluster_deployment, secret, proxy, ignition_config_override, ssh_pub_key=cluster_config.ssh_public_key
        )
        agents = self.start_nodes(nodes, infra_env, cluster_config)

        log.info("Waiting for agent status verification")
        Agent.wait_for_agents_to_install(agents)

        agent_cluster_install.wait_to_be_ready(ready=True)
        single_node_ip = get_ip_for_single_node(cluster_deployment, nodes.is_ipv4)
        nodes.controller.set_dns(api_vip=single_node_ip, ingress_vip=single_node_ip)

        log.info("waiting for agent-cluster-install to be in installing state")
        agent_cluster_install.wait_to_be_installing()

        try:
            log.info("installation started, waiting for completion")
            agent_cluster_install.wait_to_be_installed()
            agent_cluster_install.download_kubeconfig(cluster_config.kubeconfig_path)
            log.info("installation completed successfully")
        except TimeoutExpired:
            log.exception("Failure during kube-api installation flow. Collecting debug info...")
            collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install)
            raise

    @JunitTestCase()
    def capi_test(
        self,
        kube_api_context: KubeAPIContext,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        proxy_server: Optional[Callable] = None,
        *,
        is_disconnected: bool = False,
    ):
        cluster_name = cluster_config.cluster_name.get()
        api_client = kube_api_context.api_client
        spoke_namespace = kube_api_context.spoke_namespace

        secret = Secret(api_client, f"{cluster_name}-secret", spoke_namespace)
        secret.create(pull_secret=cluster_config.pull_secret)

        if is_disconnected:
            log.info("getting igntion and install config override for disconected install")
            ca_bundle = self.get_ca_bundle_from_hub(spoke_namespace)
            ignition_config_override = self.get_ignition_config_override(ca_bundle)
        else:
            ignition_config_override = None

        proxy = self.setup_proxy(nodes, cluster_config, proxy_server)

        infra_env = InfraEnv(api_client, f"{cluster_name}-infra-env", spoke_namespace)
        infra_env.create(
            cluster_deployment=None,
            ignition_config_override=ignition_config_override,
            secret=secret,
            proxy=proxy,
            ssh_pub_key=cluster_config.ssh_public_key,
        )
        self.start_nodes(nodes, infra_env, cluster_config)
        hypershift = HyperShift(name=cluster_name, kube_api_client=api_client)

        with utils.pull_secret_file() as ps:
            with tempfile.NamedTemporaryFile(mode="w") as f:
                f.write(cluster_config.ssh_public_key)
                f.flush()
                ssh_public_key_file = f.name
                hypershift.create(
                    pull_secret_file=ps,
                    agent_namespace=spoke_namespace,
                    provider_image=os.environ.get("PROVIDER_IMAGE", ""),
                    ssh_key=ssh_public_key_file,
                )

        hypershift.wait_for_control_plane_ready()

        cluster_deployment = ClusterDeployment(api_client, cluster_name, f"clusters-{cluster_name}")

        def _cluster_deployment_installed() -> bool:
            return cluster_deployment.get().get("spec", {}).get("installed")

        waiting.wait(
            _cluster_deployment_installed,
            sleep_seconds=1,
            timeout_seconds=60,
            waiting_for="clusterDeployment to get created",
            expected_exceptions=Exception,
        )
        hypershift.wait_for_control_plane_ready()
        self.set_node_count_and_wait_for_ready_nodes(cluster_deployment, hypershift, spoke_namespace, node_count=1)
        self.set_node_count_and_wait_for_ready_nodes(cluster_deployment, hypershift, spoke_namespace, node_count=2)

    @classmethod
    def set_node_count_and_wait_for_ready_nodes(
        cls, cluster_deployment: ClusterDeployment, hypershift: HyperShift, spoke_namespace: str, node_count: int
    ):
        log.info("Setting node count to %s", node_count)
        hypershift.set_nodepool_node_count(node_count)
        log.info("waiting for capi provider to set clusterDeployment ref on the agent")
        agents = cluster_deployment.wait_for_agents(node_count, agents_namespace=spoke_namespace)
        log.info("Waiting for agents status verification")
        Agent.wait_for_agents_to_install(agents)
        log.info("Waiting for node to join the cluster")
        hypershift.wait_for_nodes(node_count)
        log.info("Waiting for node to become ready")
        hypershift.wait_for_nodes(node_count, ready=True)

    @classmethod
    def setup_proxy(
        cls,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        proxy_server: Optional[Callable] = None,
    ):
        if not proxy_server:
            return None
        log.info("setting cluster proxy details")
        proxy = cls.get_proxy(nodes, cluster_config, proxy_server, Proxy)
        return proxy

    @classmethod
    def get_ca_bundle_from_hub(cls, spoke_namespace: str) -> str:
        os.environ["KUBECONFIG"] = global_variables.installer_kubeconfig_path
        with oc.project(spoke_namespace):
            ca_config_map_objects = oc.selector("configmap/registry-ca").objects()
            assert len(ca_config_map_objects) > 0
            ca_config_map_object = ca_config_map_objects[0]
            ca_bundle = ca_config_map_object.model.data["ca-bundle.crt"]
        return ca_bundle

    @classmethod
    def patch_install_config_with_ca_bundle(cls, cluster_deployment: ClusterDeployment, ca_bundle: str):
        ca_bundle_json_string = json.dumps({"additionalTrustBundle": ca_bundle})
        cluster_deployment.annotate_install_config(ca_bundle_json_string)

    @classmethod
    def get_ignition_config_override(cls, ca_bundle: str):
        ca_bundle_b64 = base64.b64encode(ca_bundle.encode()).decode()
        ignition_config_override = {
            "ignition": {"version": "3.1.0"},
            "storage": {
                "files": [
                    {
                        "path": "/etc/pki/ca-trust/source/anchors/domain.crt",
                        "mode": 420,
                        "overwrite": True,
                        "user": {"name": "root"},
                        "contents": {"source": f"data:text/plain;base64,{ca_bundle_b64}"},
                    }
                ]
            },
        }
        return json.dumps(ignition_config_override)


class TestLateBinding(BaseKubeAPI):
    @pytest.fixture
    def highly_available_controller_configuration(self, prepared_controller_configuration: BaseNodeConfig):
        self._configure_highly_available(prepared_controller_configuration)
        yield prepared_controller_configuration

    @pytest.fixture
    def kube_test_configs_late_binding_single_node(self, infraenv_configuration, controller_configuration):
        self._configure_single_node(controller_configuration)
        yield infraenv_configuration, controller_configuration

    @pytest.fixture
    def kube_test_configs_late_binding_highly_available(self, infraenv_configuration, controller_configuration):
        self._configure_highly_available(controller_configuration)
        yield infraenv_configuration, controller_configuration

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_infraenv(
        self,
        kube_test_configs_late_binding_single_node,
        kube_api_context,
        prepare_infraenv_nodes_network,
        infra_env_configuration,
    ):
        infra_env = self.kube_api_test_prepare_late_binding_infraenv(
            kube_api_context, prepare_infraenv_nodes_network, infra_env_configuration
        )
        yield infra_env, prepare_infraenv_nodes_network

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_highly_available_infraenv(
        self,
        kube_test_configs_late_binding_highly_available,
        kube_api_context,
        prepare_infraenv_nodes_network,
        infra_env_configuration,
    ):
        infra_env = self.kube_api_test_prepare_late_binding_infraenv(
            kube_api_context, prepare_infraenv_nodes_network, infra_env_configuration
        )
        yield infra_env, prepare_infraenv_nodes_network

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_cluster(self, cluster_configuration, kube_api_context, trigger_configurations):
        yield self.prepare_late_binding_cluster(
            kube_api_context,
            cluster_configuration,
            num_controlplane_agents=1,
            hold_installation=global_variables.hold_installation,
        )

    @pytest.fixture
    @JunitFixtureTestCase()
    @pytest.mark.override_controller_configuration(highly_available_controller_configuration.__name__)
    def unbound_highly_available_cluster(self, cluster_configuration, kube_api_context):
        yield self.prepare_late_binding_cluster(kube_api_context, cluster_configuration, num_controlplane_agents=3)

    @classmethod
    @JunitTestCase()
    def _late_binding_install(
        cls,
        cluster_deployment: ClusterDeployment,
        agent_cluster_install: AgentClusterInstall,
        agents: List["Agent"],
        nodes: Nodes,
        hold_installation: bool = False,
    ) -> None:
        cls._bind_all(cluster_deployment, agents)
        cls._set_agent_cluster_install_machine_cidr(agent_cluster_install, nodes)

        if len(nodes) == 1:
            cls.set_single_node_ip(cluster_deployment, nodes)

        agent_cluster_install.wait_to_be_ready(ready=True)
        Agent.wait_for_agents_to_be_bound(agents)
        if not hold_installation:
            cls._wait_for_install(agent_cluster_install, agents)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_late_binding_kube_api_sno(self, unbound_single_node_cluster, unbound_single_node_infraenv):
        infra_env, nodes = unbound_single_node_infraenv
        cluster_deployment, agent_cluster_install, cluster_config = unbound_single_node_cluster

        agents = infra_env.wait_for_agents(len(nodes))
        assert len(agents) == 1, f"Expected only one agent, found {len(agents)}"

        self._late_binding_install(
            cluster_deployment, agent_cluster_install, agents, nodes, global_variables.hold_installation
        )

        if global_variables.hold_installation:
            cluster_deployment.delete()
            Agent.wait_for_agents_to_unbound(agents)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_late_binding_kube_api_ipv4_highly_available(
        self, unbound_highly_available_cluster, unbound_highly_available_infraenv
    ):
        infra_env, nodes = unbound_highly_available_infraenv
        cluster_deployment, agent_cluster_install, cluster_config = unbound_highly_available_cluster

        agents: List[Agent] = infra_env.wait_for_agents(len(nodes))
        assert len(agents) == len(nodes), f"Expected {len(nodes)} agents, found {len(agents)}"

        api_vip, ingress_vip = self._get_vips(nodes)
        agent_cluster_install.set_api_vip(api_vip)
        agent_cluster_install.set_ingress_vip(ingress_vip)

        self._late_binding_install(cluster_deployment, agent_cluster_install, agents, nodes)

    @JunitTestCase()
    def prepare_late_binding_cluster(
        self,
        kube_api_context: KubeAPIContext,
        cluster_config: ClusterConfig,
        num_controlplane_agents: int,
        *,
        hold_installation: bool = False,
    ) -> (ClusterDeployment, AgentClusterInstall, ClusterConfig):
        cluster_name = cluster_config.cluster_name.get()
        api_client = kube_api_context.api_client
        spoke_namespace = kube_api_context.spoke_namespace

        agent_cluster_install = AgentClusterInstall(
            api_client, f"{cluster_name}-agent-cluster-install", spoke_namespace
        )

        secret = Secret(api_client, f"{cluster_name}-secret", spoke_namespace)
        secret.create(pull_secret=cluster_config.pull_secret)

        cluster_deployment = ClusterDeployment(api_client, cluster_name, spoke_namespace)
        cluster_deployment.create(agent_cluster_install_ref=agent_cluster_install.ref, secret=secret)

        agent_cluster_install.create(
            cluster_deployment_ref=cluster_deployment.ref,
            image_set_ref=self.deploy_image_set(cluster_name, api_client),
            cluster_cidr=cluster_config.cluster_networks[0].cidr,
            host_prefix=cluster_config.cluster_networks[0].host_prefix,
            service_network=cluster_config.service_networks[0].cidr,
            ssh_pub_key=cluster_config.ssh_public_key,
            hyperthreading=cluster_config.hyperthreading,
            control_plane_agents=num_controlplane_agents,
            hold_installation=hold_installation,
            worker_agents=0,
        )
        agent_cluster_install.wait_to_be_ready(ready=False)

        return cluster_deployment, agent_cluster_install, cluster_config

    def kube_api_test_prepare_late_binding_infraenv(
        self, kube_api_context: KubeAPIContext, nodes: Nodes, infraenv_config: InfraEnvConfig
    ):
        api_client = kube_api_context.api_client
        spoke_namespace = kube_api_context.spoke_namespace

        infraenv_name = infraenv_config.entity_name.get()
        spoke_namespace = spoke_namespace
        secret = Secret(api_client, f"{infraenv_name}-secret", spoke_namespace)
        secret.create(pull_secret=infraenv_config.pull_secret)

        ignition_config_override = None

        infra_env = InfraEnv(api_client, f"{infraenv_name}-infra-env", spoke_namespace)
        infra_env.create(
            cluster_deployment=None,
            ignition_config_override=ignition_config_override,
            secret=secret,
            proxy=None,
            ssh_pub_key=infraenv_config.ssh_public_key,
        )

        agents = self.start_nodes(nodes, infra_env, infraenv_config)

        log.info("Waiting for agent status verification")
        Agent.wait_for_agents_to_be_ready_for_install(agents)

        return infra_env
