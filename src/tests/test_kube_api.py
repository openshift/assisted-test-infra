import base64
import json
import os
import tempfile
from typing import Callable, List, Optional

import openshift_client as oc
import pytest
import waiting
from junit_report import JunitFixtureTestCase, JunitTestCase, JunitTestSuite
from netaddr import IPNetwork

import consts
from assisted_test_infra.test_infra import BaseInfraEnvConfig, utils
from assisted_test_infra.test_infra.controllers.load_balancer_controller import LoadBalancerController
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
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
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from assisted_test_infra.test_infra.utils.k8s_utils import get_field_from_resource
from assisted_test_infra.test_infra.utils.kubeapi_utils import get_ip_for_single_node, get_platform_type
from service_client import log
from tests.base_kubeapi_test import BaseKubeAPI
from tests.config import ClusterConfig, InfraEnvConfig, global_variables


class TestKubeAPI(BaseKubeAPI):
    KUBEAPI_IP_OPTIONS = [(False, True), (True, False)]

    @pytest.fixture
    def sno_controller_configuration(self, prepared_controller_configuration: BaseNodesConfig) -> BaseNodesConfig:
        self._configure_single_node(prepared_controller_configuration)
        yield prepared_controller_configuration

    @pytest.fixture
    def highly_available_controller_configuration(self, prepared_controller_configuration: BaseNodesConfig):
        self._configure_highly_available(prepared_controller_configuration)
        yield prepared_controller_configuration

    @pytest.mark.kube_api
    @JunitTestSuite()
    @pytest.mark.parametrize("is_ipv4, is_ipv6", utils.get_kubeapi_protocol_options())
    def test_kubeapi(
        self,
        cluster_configuration: ClusterConfig,
        kube_api_context: KubeAPIContext,
        proxy_server: Callable,
        prepared_controller_configuration: BaseNodesConfig,
        prepare_nodes_network: Nodes,
        is_ipv4: bool,
        is_ipv6: bool,
        infra_env_configuration: BaseInfraEnvConfig,
    ):
        self.kube_api_test(
            kube_api_context,
            prepare_nodes_network,
            cluster_configuration,
            prepared_controller_configuration,
            infra_env_configuration,
            proxy_server if cluster_configuration.is_ipv6 else None,
            is_disconnected=cluster_configuration.is_disconnected,
        )

    @JunitTestSuite()
    @pytest.mark.kube_api
    @pytest.mark.override_controller_configuration(highly_available_controller_configuration.__name__)
    def test_capi_provider(
        self, cluster_configuration, kube_api_context, prepare_nodes_network, infra_env_configuration
    ):
        self.capi_test(
            kube_api_context, prepare_nodes_network, cluster_configuration, infra_env_configuration.is_static_ip
        )

    @JunitTestCase()
    def kube_api_test(
        self,
        kube_api_context: KubeAPIContext,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        prepared_controller_configuration: BaseNodesConfig,
        infra_env_configuration: BaseInfraEnvConfig,
        proxy_server: Optional[Callable] = None,
        *,
        is_disconnected: bool = False,
    ):
        cluster_name = cluster_config.cluster_name.get()
        api_client = kube_api_context.api_client
        spoke_namespace = kube_api_context.spoke_namespace

        # TODO resolve it from the service if the node controller doesn't have this information
        #  (please see cluster.get_primary_machine_cidr())

        agent_cluster_install = AgentClusterInstall(
            api_client, f"{cluster_name}-agent-cluster-install", spoke_namespace
        )

        secret = Secret(api_client, f"{cluster_name}-secret", spoke_namespace)
        secret.create(pull_secret=cluster_config.pull_secret)

        cluster_deployment = ClusterDeployment(api_client, cluster_name, spoke_namespace)
        cluster_deployment.create(
            agent_cluster_install_ref=agent_cluster_install.ref,
            secret=secret,
            base_domain=global_variables.base_dns_domain,
        )
        proxy = self.setup_proxy(nodes, cluster_config, proxy_server)
        ignition_config_override = None
        infra_env = InfraEnv(api_client, f"{cluster_name}-infra-env", spoke_namespace)
        infraenv = infra_env.create(
            cluster_deployment, secret, proxy, ignition_config_override, ssh_pub_key=cluster_config.ssh_public_key
        )
        if is_disconnected and cluster_config.registry_ca_path is not None:
            log.info("setting additional trust bundle for disconnected install")
            registry_ca = None
            with open(cluster_config.registry_ca_path, "r") as f:
                registry_ca = f.read()
            if registry_ca:
                infra_env.patch(cluster_deployment=None, secret=None, additionalTrustBundle=registry_ca)

        cluster_config.iso_download_path = utils.get_iso_download_path(infraenv.get("metadata", {}).get("name"))
        nodes.prepare_nodes()

        load_balancer_type = (
            consts.LoadBalancerType.USER_MANAGED_K8S_API.value
            if cluster_config.load_balancer_type == consts.LoadBalancerType.USER_MANAGED.value
            else consts.LoadBalancerType.CLUSTER_MANAGED_K8S_API.value
        )

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
            proxy=proxy.as_dict() if proxy else {},
            platform_type=get_platform_type(cluster_config.platform),
            load_balancer_type=load_balancer_type,
        )

        agent_cluster_install.wait_to_be_ready(ready=False)

        if infra_env_configuration.is_static_ip:
            self.apply_static_network_config(kube_api_context, nodes, cluster_name, infra_env_configuration)

        agents = self.start_nodes(nodes, infra_env, cluster_config, infra_env_configuration.is_static_ip)

        self._set_agent_cluster_install_machine_cidr(agent_cluster_install, nodes)

        if len(nodes) == 1:
            # wait till the ip is set for the node and read it from its inventory
            single_node_ip = get_ip_for_single_node(cluster_deployment, nodes.is_ipv4)
            nodes.controller.tf.change_variables(
                {
                    "single_node_ip": single_node_ip,
                    "bootstrap_in_place": True,
                }
            )
            api_vip = ingress_vip = single_node_ip
        elif cluster_config.load_balancer_type == consts.LoadBalancerType.USER_MANAGED.value:
            log.info("Configuring user managed load balancer")
            load_balancer_ip = self.configure_load_balancer(
                nodes=nodes, infraenv=infra_env, aci=agent_cluster_install, cluster_config=cluster_config
            )
            api_vip = ingress_vip = load_balancer_ip
            agent_cluster_install.set_api_vip(api_vip)
            agent_cluster_install.set_ingress_vip(ingress_vip)
            primary_machine_cidr = nodes.controller.get_primary_machine_cidr()
            provisioning_machine_cidr = nodes.controller.get_provisioning_cidr()
            agent_cluster_install.set_machine_networks(
                [primary_machine_cidr, provisioning_machine_cidr, consts.DEFAULT_LOAD_BALANCER_NETWORK_CIDR]
            )
        else:
            access_vips = nodes.controller.get_ingress_and_api_vips()
            api_vip = access_vips["api_vips"][0].get("ip", "") if len(access_vips["api_vips"]) > 0 else ""
            ingress_vip = access_vips["ingress_vips"][0].get("ip", "") if len(access_vips["ingress_vips"]) > 0 else ""

            agent_cluster_install.set_api_vip(api_vip)
            agent_cluster_install.set_ingress_vip(ingress_vip)

        nodes.controller.set_dns(api_ip=api_vip, ingress_ip=ingress_vip)

        log.info("Waiting for install")
        self._wait_for_install(agent_cluster_install, agents, cluster_config.kubeconfig_path)

    def wait_for_agent_role(self, agent: Agent) -> str:
        def does_agent_has_role() -> bool:
            log.info("Waiting for agent role to become master or worker...")
            role = get_field_from_resource(resource=agent.get(), path="status.role")
            log.info(f"current role: {role}")
            return role == "master" or role == "worker"

        waiting.wait(does_agent_has_role, sleep_seconds=1, timeout_seconds=120, waiting_for="agent to get a role")

        return get_field_from_resource(resource=agent.get(), path="status.role")

    def wait_for_agent_interface(self, agent: Agent, cluster_config: ClusterConfig) -> str:
        def does_agent_has_ip() -> bool:
            log.info("waiting for agent to have IP...")
            try:
                if cluster_config.is_ipv4:
                    ip = get_field_from_resource(
                        resource=agent.get(), path="status.inventory.interfaces[0].ipV4Addresses[0]"
                    )
                elif cluster_config.is_ipv6:
                    ip = get_field_from_resource(
                        resource=agent.get(), path="status.inventory.interfaces[0].ipV6Addresses[0]"
                    )
            except ValueError:
                ip = ""

            log.info(f"current IP: {ip}")
            return ip != ""

        waiting.wait(
            does_agent_has_ip,
            sleep_seconds=1,
            timeout_seconds=60,
            waiting_for="agent to get a role",
        )

        if cluster_config.is_ipv4:
            return get_field_from_resource(resource=agent.get(), path="status.inventory.interfaces[0].ipV4Addresses[0]")
        elif cluster_config.is_ipv6:
            return get_field_from_resource(resource=agent.get(), path="status.inventory.interfaces[0].ipV6Addresses[0]")

        raise ValueError("cluster is neither IPv4 nor IPv6")

    def configure_load_balancer(
        self, nodes: Nodes, infraenv: InfraEnv, aci: AgentClusterInstall, cluster_config: ClusterConfig
    ) -> str:
        load_balancer_ip = str(IPNetwork(consts.DEFAULT_LOAD_BALANCER_NETWORK_CIDR).ip + 1)
        log.info(f"Calculated load balancer IP: {load_balancer_ip}")

        agents = infraenv.list_agents()
        master_ips = []
        worker_ips = []

        for agent in agents:
            agent_role = self.wait_for_agent_role(agent=agent)
            ip = self.wait_for_agent_interface(agent=agent, cluster_config=cluster_config)

            # remove mask
            ip = ip.split("/")[0]

            if agent_role == "master":
                master_ips.append(ip)
            elif agent_role == "worker":
                worker_ips.append(ip)

        log.info(f"master IPs: {", ".join(master_ips)}")
        log.info(f"worker IPs {", ".join(worker_ips)}")

        load_balancer_controller = LoadBalancerController(nodes.controller.tf)
        load_balancer_controller.set_load_balancing_config(
            load_balancer_ip=load_balancer_ip, master_ips=master_ips, worker_ips=worker_ips
        )

        return load_balancer_ip

    @JunitTestCase()
    def capi_test(
        self,
        kube_api_context: KubeAPIContext,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        is_static_ip: bool,
        proxy_server: Optional[Callable] = None,
        *,
        is_disconnected: bool = False,
    ):
        cluster_name = cluster_config.cluster_name.get()
        api_client = kube_api_context.api_client
        spoke_namespace = kube_api_context.spoke_namespace
        cluster_config.iso_download_path = utils.get_iso_download_path(cluster_name)
        nodes.prepare_nodes()

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
        self.start_nodes(nodes, infra_env, cluster_config, is_static_ip)
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
                    hypershift_cpo_image=os.environ.get("HYPERSHIFT_OPERATOR_IMAGE", ""),
                    release_image=os.environ.get("OPENSHIFT_INSTALL_RELEASE_IMAGE", ""),
                    ssh_key=ssh_public_key_file,
                )

        hypershift.wait_for_control_plane_ready()
        # WORKAROUND for ovn on minikube
        secret = Secret(api_client, "ovn-master-metrics-cert", hypershift.namespace)
        secret.create_with_data(secret_data={"ca_cert": "dummy data, we only need this secret to exists"})

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
        self.scale_down_nodepool_and_wait_for_unbounded_agent(
            cluster_deployment, hypershift, spoke_namespace, node_count=1
        )

    @classmethod
    def set_node_count_and_wait_for_ready_nodes(
        cls, cluster_deployment: ClusterDeployment, hypershift: HyperShift, spoke_namespace: str, node_count: int
    ):
        log.info("Setting node count to %s", node_count)
        hypershift.set_nodepool_replicas(node_count)
        log.info("waiting for capi provider to set clusterDeployment ref on the agent")
        agents = cluster_deployment.wait_for_agents(node_count, agents_namespace=spoke_namespace)
        log.info("Waiting for agents status verification")
        Agent.wait_for_agents_to_install(agents)
        log.info("Waiting for node to join the cluster")
        hypershift.wait_for_nodes(node_count)
        log.info("Waiting for node to become ready")
        hypershift.wait_for_nodes(node_count, ready=True)

    @classmethod
    def scale_down_nodepool_and_wait_for_unbounded_agent(
        cls, cluster_deployment: ClusterDeployment, hypershift: HyperShift, spoke_namespace: str, node_count: int
    ):
        agents = cluster_deployment.list_agents()
        log.info("Setting node count to %s", node_count)
        hypershift.set_nodepool_replicas(node_count)
        log.info("waiting for capi provider to remove clusterDeployment ref from the agent")
        updated_agents = cluster_deployment.wait_for_agents(node_count, agents_namespace=spoke_namespace)
        removed_agent = set(agents) - set(updated_agents)
        log.info("Agent: {} removed")
        log.info("Waiting for agent to unbind")
        Agent.wait_for_agents_to_unbound(list(removed_agent))
        log.info("Scale down completed")

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
    def highly_available_controller_configuration(self, prepared_controller_configuration: BaseNodesConfig):
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
    def kube_test_configs_late_binding_workers(self, infraenv_configuration, controller_configuration):
        self._configure_workers(controller_configuration)
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
    def unbound_workers_infraenv(
        self,
        kube_test_configs_late_binding_workers,
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
    def unbound_highly_available_cluster(self, cluster_configuration, kube_api_context, trigger_configurations):
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
        api_vip, _ = cls._get_vips(nodes)

        if len(nodes) == 1:
            single_node_ip = api_vip = get_ip_for_single_node(cluster_deployment, nodes.is_ipv4)
            nodes.controller.tf.change_variables(
                {
                    "single_node_ip": single_node_ip,
                    "bootstrap_in_place": True,
                }
            )

        # Add the API VIP DNS record to the assisted-service network
        # here so it can resolve by the time the host(s) start reclaim
        if global_variables.reclaim_hosts:
            nodes.controller.add_dns_host_to_network(
                network_name="default", api_vip=api_vip, cluster_name=cluster_deployment.ref.name
            )

        agent_cluster_install.wait_to_be_ready(ready=True)
        Agent.wait_for_agents_to_be_bound(agents)
        if not hold_installation:
            cls._wait_for_install(agent_cluster_install, agents)

    @classmethod
    @JunitTestCase()
    def _reclaim_agents(cls, agents: List["Agent"]):
        cls._unbind_all(agents)
        Agent.wait_for_agents_to_unbound(agents)
        Agent.wait_for_agents_to_reclaim(agents)

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

        if global_variables.reclaim_hosts:
            self._reclaim_agents(agents)

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
        if global_variables.reclaim_hosts:
            self._reclaim_agents(agents)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_prepare_late_binding_kube_api_ipv4_workers(self, unbound_workers_infraenv):
        infra_env, nodes = unbound_workers_infraenv
        agents: List[Agent] = infra_env.wait_for_agents(len(nodes))
        assert len(agents) == len(nodes), f"Expected {len(nodes)} agents, found {len(agents)}"

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
        infraenv_config.iso_download_path = utils.get_iso_download_path(infraenv_name)
        nodes.prepare_nodes()

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

        agents = self.start_nodes(nodes, infra_env, infraenv_config, infraenv_config.is_static_ip)

        log.info("Waiting for agent status verification")
        Agent.wait_for_agents_to_be_ready_for_install(agents)

        return infra_env
