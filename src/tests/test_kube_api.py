import base64
import json
import os
import tempfile
import uuid
from typing import Callable, List, Optional

import openshift as oc
import pytest
import waiting
from junit_report import JunitFixtureTestCase, JunitTestCase, JunitTestSuite
from kubernetes.client import ApiClient
from netaddr import IPNetwork

from assisted_test_infra.download_logs import collect_debug_info_from_cluster
from assisted_test_infra.test_infra import Nodes, utils
from assisted_test_infra.test_infra.helper_classes.hypershift import HyperShift
from assisted_test_infra.test_infra.helper_classes.kube_helpers import (
    Agent,
    AgentClusterInstall,
    ClusterDeployment,
    InfraEnv,
    Proxy,
    Secret,
)
from service_client import log
from tests.base_kubeapi_test import BaseKubeAPI
from tests.config import ClusterConfig, InfraEnvConfig, global_variables

PROXY_PORT = 3129


class TestKubeAPI(BaseKubeAPI):
    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_ipv4(self, kube_test_configs_single_node, kube_api_context, get_nodes):
        namespace = global_variables.spoke_namespace
        cluster_config, tf_config = kube_test_configs_single_node
        self.kube_api_test(kube_api_context.api_client, get_nodes(tf_config, cluster_config), cluster_config, namespace)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_ipv6(self, kube_test_configs_single_node, kube_api_context, proxy_server, get_nodes):
        cluster_config, tf_config = kube_test_configs_single_node
        self.kube_api_test(
            kube_api_context.api_client,
            get_nodes(tf_config, cluster_config),
            cluster_config,
            global_variables.spoke_namespace,
            proxy_server,
            is_ipv4=False,
        )

    def kube_api_test(
        self,
        api_client: ApiClient,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        spoke_namespace: str,
        proxy_server: Optional[Callable] = None,
        *,
        is_ipv4: bool = True,
        is_disconnected: bool = False,
    ):
        cluster_name = cluster_config.cluster_name.get()

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
        )
        agent_cluster_install.wait_to_be_ready(ready=False)

        if is_disconnected:
            log.info("getting igntion and install config override for disconected install")
            ca_bundle = self.get_ca_bundle_from_hub()
            self.patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle)
            ignition_config_override = self.get_ignition_config_override(ca_bundle)
        else:
            ignition_config_override = None

        proxy = self.setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server)

        infra_env = InfraEnv(api_client, f"{cluster_name}-infra-env", global_variables.spoke_namespace)
        infra_env.create(
            cluster_deployment, secret, proxy, ignition_config_override, ssh_pub_key=cluster_config.ssh_public_key
        )
        agents = self.start_nodes(nodes, infra_env, cluster_config, is_ipv4)

        if len(nodes) == 1:
            self.set_single_node_ip(cluster_deployment, nodes, is_ipv4)

        log.info("Waiting for agent status verification")
        Agent.wait_for_agents_to_install(agents)

        agent_cluster_install.wait_to_be_ready(ready=True)

        log.info("waiting for agent-cluster-install to be in installing state")
        agent_cluster_install.wait_to_be_installing()

        try:
            log.info("installation started, waiting for completion")
            agent_cluster_install.wait_to_be_installed()
            log.info("installation completed successfully")
        except Exception:
            log.exception("Failure during kube-api installation flow:")
            collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_capi_provider(self, kube_test_configs_highly_available, kube_api_context, get_nodes):
        cluster_config, tf_config = kube_test_configs_highly_available
        self.capi_test(kube_api_context.api_client, get_nodes(tf_config, cluster_config), cluster_config)

    def capi_test(
        self,
        api_client: ApiClient,
        nodes: Nodes,
        cluster_config: ClusterConfig,
        proxy_server: Optional[Callable] = None,
        *,
        is_ipv4: bool = True,
        is_disconnected: bool = False,
    ):
        cluster_name = cluster_config.cluster_name.get()
        spoke_namespace = global_variables.spoke_namespace

        # TODO resolve it from the service if the node controller doesn't have this information
        #  (please see cluster.get_primary_machine_cidr())
        machine_cidr = nodes.controller.get_primary_machine_cidr()

        secret = Secret(api_client, f"{cluster_name}-secret", spoke_namespace)
        secret.create(pull_secret=cluster_config.pull_secret)

        if is_disconnected:
            log.info("getting igntion and install config override for disconected install")
            ca_bundle = self.get_ca_bundle_from_hub()
            ignition_config_override = self.get_ignition_config_override(ca_bundle)
        else:
            ignition_config_override = None

        proxy = self.setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server)

        infra_env = InfraEnv(api_client, f"{cluster_name}-infra-env", spoke_namespace)
        infra_env.create(
            cluster_deployment=None,
            ignition_config_override=ignition_config_override,
            secret=secret,
            proxy=proxy,
            ssh_pub_key=cluster_config.ssh_public_key,
        )
        self.start_nodes(nodes, infra_env, cluster_config, is_ipv4)
        hypershift = HyperShift(name=cluster_name)

        with utils.pull_secret_file() as ps:
            with tempfile.NamedTemporaryFile(mode="w") as f:
                f.write(cluster_config.ssh_public_key)
                f.flush()
                ssh_public_key_file = f.name
                hypershift.create(
                    pull_secret_file=ps,
                    agent_namespace=global_variables.spoke_namespace,
                    provider_image=os.environ.get("PROVIDER_IMAGE", ""),
                    ssh_key=ssh_public_key_file,
                )

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
        self.set_node_count_and_wait_for_ready_nodes(cluster_deployment, hypershift, api_client, node_count=1)
        self.set_node_count_and_wait_for_ready_nodes(cluster_deployment, hypershift, api_client, node_count=2)

    @classmethod
    def set_node_count_and_wait_for_ready_nodes(
        cls, cluster_deployment: ClusterDeployment, hypershift: HyperShift, api_client: ApiClient, node_count: int
    ):
        log.info("Setting node count to %s", node_count)
        hypershift.set_nodepool_node_count(api_client, node_count)
        log.info("waiting for capi provider to set clusterDeployment ref on the agent")
        agents = cluster_deployment.wait_for_agents(node_count, agents_namespace=global_variables.spoke_namespace)
        log.info("Waiting for agents status verification")
        Agent.wait_for_agents_to_install(agents)
        hypershift.download_kubeconfig(api_client)
        log.info("Waiting for node to join the cluster")
        hypershift.wait_for_nodes(node_count)
        log.info("Waiting for node to become ready")
        hypershift.wait_for_nodes(node_count, ready=True)

    @classmethod
    def setup_proxy(
        cls,
        cluster_config: ClusterConfig,
        machine_cidr: str,
        cluster_name: str,
        proxy_server: Optional[Callable] = None,
    ):
        if not proxy_server:
            return
        log.info("setting cluster proxy details")
        proxy_server_name = "squid-" + str(uuid.uuid4())[:8]
        port = utils.scan_for_free_port(PROXY_PORT)
        proxy_server(name=proxy_server_name, port=port)
        host_ip = str(IPNetwork(machine_cidr).ip + 1)
        proxy_url = f"http://[{host_ip}]:{port}"
        no_proxy = ",".join(
            [
                machine_cidr,
                cluster_config.service_networks[0].cidr,
                cluster_config.cluster_networks[0].cidr,
                f".{cluster_name}.redhat.com",
            ]
        )
        return Proxy(http_proxy=proxy_url, https_proxy=proxy_url, no_proxy=no_proxy)

    @classmethod
    def get_ca_bundle_from_hub(cls) -> str:
        os.environ["KUBECONFIG"] = global_variables.installer_kubeconfig_path
        with oc.project(global_variables.spoke_namespace):
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
    def kube_test_configs_late_binding_single_node(self, infraenv_config, terraform_config):
        self._configure_single_node(terraform_config)
        yield infraenv_config, terraform_config

    @pytest.fixture
    def kube_test_configs_late_binding_highly_available(self, infraenv_config, terraform_config):
        self._configure_highly_available(terraform_config)
        yield infraenv_config, terraform_config

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_infraenv(
        self, kube_test_configs_late_binding_single_node, kube_api_context, get_nodes_infraenv
    ):
        infraenv_config, tf_config = kube_test_configs_late_binding_single_node
        nodes = get_nodes_infraenv(tf_config, infraenv_config)
        api_client = kube_api_context.api_client
        infra_env = self.kube_api_test_prepare_late_binding_infraenv(api_client, nodes, infraenv_config)

        yield infra_env, nodes

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_highly_available_infraenv(
        self, kube_test_configs_late_binding_highly_available, kube_api_context, get_nodes_infraenv
    ):
        infraenv_config, tf_config = kube_test_configs_late_binding_highly_available
        nodes = get_nodes_infraenv(tf_config, infraenv_config)
        api_client = kube_api_context.api_client
        infra_env = self.kube_api_test_prepare_late_binding_infraenv(api_client, nodes, infraenv_config)

        yield infra_env, nodes

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_cluster(self, kube_test_configs_single_node, kube_api_context):
        cluster_config, _ = kube_test_configs_single_node
        yield self.kube_api_test_prepare_late_binding_cluster(
            kube_api_context.api_client, cluster_config, num_controlplane_agents=1
        )

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_highly_available_cluster(self, kube_test_configs_highly_available, kube_api_context):
        cluster_config, _ = kube_test_configs_highly_available
        yield self.kube_api_test_prepare_late_binding_cluster(
            kube_api_context.api_client, cluster_config, num_controlplane_agents=3
        )

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_cluster_hold_installation(self, kube_test_configs_single_node, kube_api_context):
        cluster_config, _ = kube_test_configs_single_node
        api_client = kube_api_context.api_client
        yield self.kube_api_test_prepare_late_binding_cluster(
            api_client, cluster_config, num_controlplane_agents=1, hold_installation=True
        )

    @classmethod
    @JunitTestCase()
    def _late_binding_install(
        cls,
        cluster_deployment: ClusterDeployment,
        agent_cluster_install: AgentClusterInstall,
        agents: List["Agent"],
        nodes: Nodes,
        is_ipv4: bool,
        hold_installation: bool = False,
    ) -> None:
        cls._bind_all(cluster_deployment, agents)
        cls._set_agent_cluster_install_machine_cidr(agent_cluster_install, nodes)

        if len(nodes) == 1:
            cls.set_single_node_ip(cluster_deployment, nodes, is_ipv4)

        agent_cluster_install.wait_to_be_ready(ready=True)
        Agent.wait_for_agents_to_be_bound(agents)
        if not hold_installation:
            cls._wait_for_install(agent_cluster_install, agents)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_late_binding_ipv4_single_node(self, unbound_single_node_cluster, unbound_single_node_infraenv):
        infra_env, nodes = unbound_single_node_infraenv
        cluster_deployment, agent_cluster_install, cluster_config = unbound_single_node_cluster

        agents = infra_env.wait_for_agents(len(nodes))
        assert len(agents) == 1, f"Expected only one agent, found {len(agents)}"

        self._late_binding_install(cluster_deployment, agent_cluster_install, agents, nodes, is_ipv4=True)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_late_unbinding_ipv4_single_node(
        self, unbound_single_node_cluster_hold_installation, unbound_single_node_infraenv
    ):
        infra_env, nodes = unbound_single_node_infraenv
        cluster_deployment, agent_cluster_install, cluster_config = unbound_single_node_cluster_hold_installation

        agents = infra_env.wait_for_agents(len(nodes))
        self._late_binding_install(
            cluster_deployment, agent_cluster_install, agents, nodes, is_ipv4=True, hold_installation=True
        )

        cluster_deployment.delete()
        Agent.wait_for_agents_to_unbound(agents)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_late_binding_ipv4_highly_available(
        self, unbound_highly_available_cluster, unbound_highly_available_infraenv
    ):
        infra_env, nodes = unbound_highly_available_infraenv
        cluster_deployment, agent_cluster_install, cluster_config = unbound_highly_available_cluster

        agents: List[Agent] = infra_env.wait_for_agents(len(nodes))
        assert len(agents) == len(nodes), f"Expected {len(nodes)} agents, found {len(agents)}"

        api_vip, ingress_vip = self._get_vips(cluster_config, nodes)
        agent_cluster_install.set_api_vip(api_vip)
        agent_cluster_install.set_ingress_vip(ingress_vip)

        self._late_binding_install(cluster_deployment, agent_cluster_install, agents, nodes, is_ipv4=True)

    @JunitTestCase()
    def kube_api_test_prepare_late_binding_cluster(
        self,
        api_client: ApiClient,
        cluster_config: ClusterConfig,
        num_controlplane_agents: int,
        *,
        hold_installation: bool = False,
    ) -> (ClusterDeployment, AgentClusterInstall, ClusterConfig):
        cluster_name = cluster_config.cluster_name.get()
        spoke_namespace = global_variables.spoke_namespace

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
        self, api_client: ApiClient, nodes: Nodes, infraenv_config: InfraEnvConfig, *, is_ipv4: bool = True
    ):
        infraenv_name = infraenv_config.entity_name.get()
        spoke_namespace = global_variables.spoke_namespace
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

        agents = self.start_nodes(nodes, infra_env, infraenv_config, is_ipv4)

        log.info("Waiting for agent status verification")
        Agent.wait_for_agents_to_be_ready_for_install(agents)

        return infra_env
