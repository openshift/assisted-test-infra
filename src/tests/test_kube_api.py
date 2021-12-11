import base64
import json
import logging
import os
import tempfile
import uuid
from typing import List

import openshift as oc
import pytest
import waiting
from junit_report import JunitFixtureTestCase, JunitTestCase, JunitTestSuite
from netaddr import IPNetwork

from assisted_test_infra.download_logs import collect_debug_info_from_cluster
from assisted_test_infra.test_infra import Nodes, download_iso, get_openshift_release_image, utils
from assisted_test_infra.test_infra.helper_classes.hypershift import HyperShift
from assisted_test_infra.test_infra.helper_classes.kube_helpers import (
    Agent,
    AgentClusterInstall,
    ClusterDeployment,
    ClusterImageSet,
    ClusterImageSetReference,
    InfraEnv,
    Proxy,
    Secret,
)
from assisted_test_infra.test_infra.utils.kubeapi_utils import get_ip_for_single_node
from tests.base_test import BaseTest
from tests.config import ClusterConfig, InfraEnvConfig, global_variables

PROXY_PORT = 3129

logger = logging.getLogger(__name__)


class TestKubeAPI(BaseTest):
    @staticmethod
    def _configure_single_node(terraform_config):
        terraform_config.masters_count = 1
        terraform_config.workers_count = 0
        terraform_config.master_vcpu = 8
        terraform_config.master_memory = 35840

    @staticmethod
    def _configure_highly_available(terraform_config):
        terraform_config.masters_count = 3
        terraform_config.workers_count = 0
        terraform_config.master_vcpu = 4
        terraform_config.master_memory = 17920

    @pytest.fixture
    def kube_test_configs_single_node(self, configs):
        cluster_config, terraform_config = configs
        self._configure_single_node(terraform_config)
        yield cluster_config, terraform_config

    @pytest.fixture
    def kube_test_configs_highly_available(self, configs):
        cluster_config, terraform_config = configs
        self._configure_highly_available(terraform_config)
        yield cluster_config, terraform_config

    @pytest.fixture
    def kube_test_configs_late_binding_single_node(self, infraenv_config, terraform_config):
        self._configure_single_node(terraform_config)
        yield infraenv_config, terraform_config

    @pytest.fixture
    def kube_test_configs_late_binding_highly_available(self, infraenv_config, terraform_config):
        self._configure_highly_available(terraform_config)
        yield infraenv_config, terraform_config

    @classmethod
    def _get_vips(cls, cluster_config, nodes: Nodes):
        main_cidr = nodes.controller.get_primary_machine_cidr()

        # Arbitrarily choose 3, 4 (e.g. 192.168.128.3 and 192.168.128.4) for the VIPs
        # Terraform/libvirt allocates IPs in the 10+ range so these should be safe to use
        # TODO: Find a more robust solution to choose the VIPs. KubeAPI Assisted does not do
        #  DHCP for VIPs.
        api_vip = str(IPNetwork(main_cidr).ip + 3)
        ingress_vip = str(IPNetwork(main_cidr).ip + 4)

        return api_vip, ingress_vip

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_infraenv(
        self, kube_test_configs_late_binding_single_node, kube_api_context, get_nodes_infraenv
    ):
        infraenv_config, tf_config = kube_test_configs_late_binding_single_node
        nodes = get_nodes_infraenv(tf_config, infraenv_config)
        infra_env = kube_api_test_prepare_late_binding_infraenv(kube_api_context, nodes, infraenv_config)

        yield infra_env, nodes

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_highly_available_infraenv(
        self, kube_test_configs_late_binding_highly_available, kube_api_context, get_nodes_infraenv
    ):
        infraenv_config, tf_config = kube_test_configs_late_binding_highly_available
        nodes = get_nodes_infraenv(tf_config, infraenv_config)
        infra_env = kube_api_test_prepare_late_binding_infraenv(kube_api_context, nodes, infraenv_config)

        yield infra_env, nodes

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_single_node_cluster(self, kube_test_configs_single_node, kube_api_context):
        cluster_config, _ = kube_test_configs_single_node
        yield kube_api_test_prepare_late_binding_cluster(
            kube_api_context=kube_api_context, cluster_config=cluster_config, num_controlplane_agents=1
        )

    @pytest.fixture
    @JunitFixtureTestCase()
    def unbound_highly_available_cluster(self, kube_test_configs_highly_available, kube_api_context):
        cluster_config, _ = kube_test_configs_highly_available
        yield kube_api_test_prepare_late_binding_cluster(
            kube_api_context=kube_api_context, cluster_config=cluster_config, num_controlplane_agents=3
        )

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_ipv4(self, kube_test_configs_single_node, kube_api_context, get_nodes):
        cluster_config, tf_config = kube_test_configs_single_node
        kube_api_test(kube_api_context, get_nodes(tf_config, cluster_config), cluster_config)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_ipv6(self, kube_test_configs_single_node, kube_api_context, proxy_server, get_nodes):
        cluster_config, tf_config = kube_test_configs_single_node
        tf_config.is_ipv6 = True
        tf_config.is_ipv4 = False

        kube_api_test(
            kube_api_context, get_nodes(tf_config, cluster_config), cluster_config, proxy_server, is_ipv4=False
        )

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_capi_provider(self, kube_test_configs_single_node, kube_api_context, get_nodes):
        cluster_config, tf_config = kube_test_configs_single_node
        capi_test(kube_api_context, get_nodes(tf_config, cluster_config), cluster_config)

    @staticmethod
    def _bind_all(cluster_deployment, agents):
        for agent in agents:
            agent.bind(cluster_deployment)

    @staticmethod
    def _wait_for_install(agent_cluster_install, agents):
        agent_cluster_install.wait_to_be_ready(True)
        agent_cluster_install.wait_to_be_installing()
        Agent.wait_for_agents_to_install(agents)
        agent_cluster_install.wait_to_be_installed()

    @staticmethod
    def _set_agent_cluster_install_machine_cidr(agent_cluster_install, nodes):
        machine_cidr = nodes.controller.get_primary_machine_cidr()
        agent_cluster_install.set_machinenetwork(machine_cidr)

    @classmethod
    def _late_binding_install(cls, cluster_deployment, agent_cluster_install, agents, nodes, is_ipv4):
        cls._bind_all(cluster_deployment, agents)
        cls._set_agent_cluster_install_machine_cidr(agent_cluster_install, nodes)

        if len(nodes) == 1:
            set_single_node_ip(cluster_deployment, nodes, is_ipv4=is_ipv4)

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
    kube_api_context, cluster_config: ClusterConfig, num_controlplane_agents, *, proxy_server=None, is_ipv4=True
):
    cluster_name = cluster_config.cluster_name.get()

    agent_cluster_install = AgentClusterInstall(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-agent-cluster-install",
        namespace=global_variables.spoke_namespace,
    )

    secret = Secret(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-secret",
        namespace=global_variables.spoke_namespace,
    )
    secret.create(pull_secret=cluster_config.pull_secret)

    cluster_deployment = ClusterDeployment(
        kube_api_client=kube_api_context.api_client,
        name=cluster_name,
        namespace=global_variables.spoke_namespace,
    )
    cluster_deployment.create(
        agent_cluster_install_ref=agent_cluster_install.ref,
        secret=secret,
    )

    agent_cluster_install.create(
        cluster_deployment_ref=cluster_deployment.ref,
        image_set_ref=deploy_image_set(cluster_name, kube_api_context),
        cluster_cidr=cluster_config.cluster_networks[0].cidr,
        host_prefix=cluster_config.cluster_networks[0].host_prefix,
        service_network=cluster_config.service_networks[0].cidr,
        ssh_pub_key=cluster_config.ssh_public_key,
        hyperthreading=cluster_config.hyperthreading,
        control_plane_agents=num_controlplane_agents,
        worker_agents=0,
    )
    agent_cluster_install.wait_to_be_ready(False)

    return cluster_deployment, agent_cluster_install, cluster_config


def kube_api_test_prepare_late_binding_infraenv(
    kube_api_context, nodes: Nodes, infraenv_config: InfraEnvConfig, *, is_ipv4=True
):
    infraenv_name = infraenv_config.entity_name.get()

    secret = Secret(
        kube_api_client=kube_api_context.api_client,
        name=f"{infraenv_name}-secret",
        namespace=global_variables.spoke_namespace,
    )
    secret.create(pull_secret=infraenv_config.pull_secret)

    ignition_config_override = None

    infra_env = InfraEnv(
        kube_api_client=kube_api_context.api_client,
        name=f"{infraenv_name}-infra-env",
        namespace=global_variables.spoke_namespace,
    )
    infra_env.create(
        cluster_deployment=None,
        ignition_config_override=ignition_config_override,
        secret=secret,
        proxy=None,
        ssh_pub_key=infraenv_config.ssh_public_key,
    )

    infra_env.status()

    download_iso_from_infra_env(infra_env, infraenv_config.iso_download_path)

    logger.info("iso downloaded, starting nodes")
    nodes.start_all()

    logger.info("waiting for host agent")
    agents = infra_env.wait_for_agents(len(nodes))
    for agent in agents:
        agent.approve()
        set_agent_hostname(nodes[0], agent, is_ipv4)  # Currently only supports single node

    logger.info("Waiting for agent status verification")
    Agent.wait_for_agents_to_be_ready_for_install(agents)

    return infra_env


def capi_test(
    kube_api_context,
    nodes: Nodes,
    cluster_config: ClusterConfig,
    proxy_server=None,
    *,
    is_ipv4=True,
    is_disconnected=False,
):
    cluster_name = cluster_config.cluster_name.get()

    # TODO resolve it from the service if the node controller doesn't have this information
    #  (please see cluster.get_primary_machine_cidr())
    machine_cidr = nodes.controller.get_primary_machine_cidr()

    secret = Secret(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-secret",
        namespace=global_variables.spoke_namespace,
    )
    secret.create(pull_secret=cluster_config.pull_secret)

    if is_disconnected:
        logger.info("getting igntion and install config override for disconected install")
        ca_bundle = get_ca_bundle_from_hub()
        ignition_config_override = get_ignition_config_override(ca_bundle)
    else:
        ignition_config_override = None

    proxy = setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server)

    infra_env = InfraEnv(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-infra-env",
        namespace=global_variables.spoke_namespace,
    )
    infra_env.create(
        cluster_deployment=None,
        ignition_config_override=ignition_config_override,
        secret=secret,
        proxy=proxy,
        ssh_pub_key=cluster_config.ssh_public_key,
    )
    infra_env.status()
    download_iso_from_infra_env(infra_env, cluster_config.iso_download_path)

    logger.info("iso downloaded, starting nodes")
    nodes.start_all()

    logger.info("waiting for host agent")
    agents = infra_env.wait_for_agents(len(nodes))
    for agent in agents:
        agent.approve()
        set_agent_hostname(nodes[0], agent, is_ipv4)

    hypershift = HyperShift(name=cluster_name)

    with utils.pull_secret_file() as ps:
        with tempfile.NamedTemporaryFile(mode="w") as f:
            f.write(cluster_config.ssh_public_key)
            f.flush()
            ssh_public_key_file = f.name
            hypershift.create(pull_secret_file=ps, ssh_key=ssh_public_key_file)

    cluster_deployment = ClusterDeployment(
        kube_api_client=kube_api_context.api_client, name=cluster_name, namespace=f"clusters-{cluster_name}"
    )

    def _cluster_deployment_installed() -> bool:
        return cluster_deployment.get().get("spec", {}).get("installed")

    waiting.wait(
        _cluster_deployment_installed,
        sleep_seconds=1,
        timeout_seconds=60,
        waiting_for="clusterDeployment to get created",
        expected_exceptions=Exception,
    )
    node_count = 1
    hypershift.set_nodepool_node_count(kube_api_context.api_client, node_count)
    logger.info("waiting for capi provider to set clusterDeployment ref on the agent")
    agents = cluster_deployment.wait_for_agents(node_count, agents_namespace=global_variables.spoke_namespace)

    logger.info("Waiting for agent status verification")
    for agent in agents:
        agent.wait_for_agents_to_install(agents)

    hypershift.download_kubeconfig(kube_api_context.api_client)

    logger.info("Waiting for node to join the cluster")
    hypershift.wait_for_nodes(node_count)
    # TODO: validate node is ready
    logger.info("Waiting for node to become ready")
    hypershift.wait_for_nodes(node_count, ready=True)


def kube_api_test(
    kube_api_context,
    nodes: Nodes,
    cluster_config: ClusterConfig,
    proxy_server=None,
    *,
    is_ipv4=True,
    is_disconnected=False,
):
    cluster_name = cluster_config.cluster_name.get()

    # TODO resolve it from the service if the node controller doesn't have this information
    #  (please see cluster.get_primary_machine_cidr())
    machine_cidr = nodes.controller.get_primary_machine_cidr()

    agent_cluster_install = AgentClusterInstall(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-agent-cluster-install",
        namespace=global_variables.spoke_namespace,
    )

    secret = Secret(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-secret",
        namespace=global_variables.spoke_namespace,
    )
    secret.create(pull_secret=cluster_config.pull_secret)

    cluster_deployment = ClusterDeployment(
        kube_api_client=kube_api_context.api_client,
        name=cluster_name,
        namespace=global_variables.spoke_namespace,
    )
    cluster_deployment.create(
        agent_cluster_install_ref=agent_cluster_install.ref,
        secret=secret,
    )

    agent_cluster_install.create(
        cluster_deployment_ref=cluster_deployment.ref,
        image_set_ref=deploy_image_set(cluster_name, kube_api_context),
        cluster_cidr=cluster_config.cluster_networks[0].cidr,
        host_prefix=cluster_config.cluster_networks[0].host_prefix,
        service_network=cluster_config.service_networks[0].cidr,
        ssh_pub_key=cluster_config.ssh_public_key,
        hyperthreading=cluster_config.hyperthreading,
        control_plane_agents=nodes.controller.params.master_count,
        worker_agents=nodes.controller.params.worker_count,
        machine_cidr=machine_cidr,
    )
    agent_cluster_install.wait_to_be_ready(False)

    if is_disconnected:
        logger.info("getting igntion and install config override for disconected install")
        ca_bundle = get_ca_bundle_from_hub()
        patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle)
        ignition_config_override = get_ignition_config_override(ca_bundle)
    else:
        ignition_config_override = None

    proxy = setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server)

    infra_env = InfraEnv(
        kube_api_client=kube_api_context.api_client,
        name=f"{cluster_name}-infra-env",
        namespace=global_variables.spoke_namespace,
    )
    infra_env.create(
        cluster_deployment=cluster_deployment,
        ignition_config_override=ignition_config_override,
        secret=secret,
        proxy=proxy,
        ssh_pub_key=cluster_config.ssh_public_key,
    )
    infra_env.status()
    download_iso_from_infra_env(infra_env, cluster_config.iso_download_path)

    logger.info("iso downloaded, starting nodes")
    nodes.start_all()

    logger.info("waiting for host agent")
    agents = cluster_deployment.wait_for_agents(len(nodes))
    for agent in agents:
        agent.approve()
        set_agent_hostname(nodes[0], agent, is_ipv4)  # Currently only supports single node

    if len(nodes) == 1:
        set_single_node_ip(cluster_deployment, nodes, is_ipv4)

    logger.info("Waiting for agent status verification")
    Agent.wait_for_agents_to_install(agents)

    agent_cluster_install.wait_to_be_ready(True)

    logger.info("waiting for agent-cluster-install to be in installing state")
    agent_cluster_install.wait_to_be_installing()

    try:
        logger.info("installation started, waiting for completion")
        agent_cluster_install.wait_to_be_installed()
        logger.info("installation completed successfully")
    except Exception:
        logger.exception("Failure during kube-api installation flow:")
        collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install)


def deploy_image_set(cluster_name, kube_api_context):
    openshift_release_image = get_openshift_release_image()

    image_set_name = f"{cluster_name}-image-set"
    image_set = ClusterImageSet(
        kube_api_client=kube_api_context.api_client,
        name=image_set_name,
    )
    image_set.create(openshift_release_image)

    return ClusterImageSetReference(image_set_name)


def setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server=None):
    if not proxy_server:
        return
    logger.info("setting cluster proxy details")
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


def download_iso_from_infra_env(infra_env, iso_download_path):
    logger.info("getting iso download url")
    iso_download_url = infra_env.get_iso_download_url()
    logger.info("downloading iso from url=%s", iso_download_url)
    download_iso(iso_download_url, iso_download_path)
    assert os.path.isfile(iso_download_path)


def set_single_node_ip(cluster_deployment, nodes, is_ipv4):
    logger.info("waiting to have host single node ip")
    single_node_ip = get_ip_for_single_node(cluster_deployment, is_ipv4)
    nodes.controller.tf.change_variables(
        {
            "single_node_ip": single_node_ip,
            "bootstrap_in_place": True,
        }
    )
    logger.info("single node ip=%s", single_node_ip)


def set_agent_hostname(node, agent, is_ipv4):
    if is_ipv4:
        return
    logger.info("patching agent hostname=%s", node)
    agent.patch(hostname=node.name)


def get_ca_bundle_from_hub():
    os.environ["KUBECONFIG"] = global_variables.installer_kubeconfig_path
    with oc.project(global_variables.spoke_namespace):
        ca_config_map_objects = oc.selector("configmap/registry-ca").objects()
        assert len(ca_config_map_objects) > 0
        ca_config_map_object = ca_config_map_objects[0]
        ca_bundle = ca_config_map_object.model.data["ca-bundle.crt"]
    return ca_bundle


def patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle):
    ca_bundle_json_string = json.dumps({"additionalTrustBundle": ca_bundle})
    cluster_deployment.annotate_install_config(ca_bundle_json_string)


def get_ignition_config_override(ca_bundle):
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
