import os
from typing import List, Optional

import pytest
import waiting
import yaml
from junit_report import JunitFixtureTestCase, JunitTestCase
from kubernetes.client import ApiClient, CoreV1Api
from kubernetes.client.exceptions import ApiException as K8sApiException
from netaddr import IPNetwork

from assisted_test_infra.test_infra import BaseEntityConfig, BaseInfraEnvConfig, Nodes, utils
from assisted_test_infra.test_infra.controllers import Node
from assisted_test_infra.test_infra.helper_classes.config import BaseNodesConfig
from assisted_test_infra.test_infra.helper_classes.kube_helpers import (
    Agent,
    AgentClusterInstall,
    ClusterDeployment,
    ClusterImageSet,
    ClusterImageSetReference,
    InfraEnv,
    KubeAPIContext,
    NMStateConfig,
)
from assisted_test_infra.test_infra.tools import static_network
from assisted_test_infra.test_infra.utils.entity_name import SpokeClusterNamespace
from consts.consts import MiB_UNITS
from service_client import ClientFactory, log
from tests.base_test import BaseTest
from tests.config import global_variables


class BaseKubeAPI(BaseTest):
    @pytest.fixture(scope="session")
    def kube_api_client(self):
        yield ClientFactory.create_kube_api_client()

    @pytest.fixture()
    def spoke_namespace(self):
        yield SpokeClusterNamespace().get()

    @pytest.fixture()
    @JunitFixtureTestCase()
    def kube_api_context(self, kube_api_client, spoke_namespace):
        kube_api_context = KubeAPIContext(
            kube_api_client, clean_on_exit=global_variables.test_teardown, spoke_namespace=spoke_namespace
        )

        with kube_api_context:
            v1 = CoreV1Api(kube_api_client)

            try:
                v1.create_namespace(
                    body={
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": spoke_namespace,
                            "labels": {
                                "name": spoke_namespace,
                            },
                        },
                    }
                )
            except K8sApiException as e:
                if e.status != 409:
                    raise

            yield kube_api_context

            if global_variables.test_teardown:
                v1.delete_namespace(spoke_namespace)

    @pytest.fixture
    @JunitFixtureTestCase()
    def kube_test_configs_highly_available(self, cluster_configuration, controller_configuration):
        self._configure_highly_available(controller_configuration)
        yield cluster_configuration, controller_configuration

    @staticmethod
    def _configure_single_node(terraform_config: BaseNodesConfig):
        terraform_config.masters_count = 1
        terraform_config.workers_count = 0
        terraform_config.master_vcpu = 8
        terraform_config.master_memory = 16 * MiB_UNITS

    @staticmethod
    def _configure_highly_available(terraform_config: BaseNodesConfig):
        terraform_config.masters_count = 3
        terraform_config.workers_count = 0
        terraform_config.master_vcpu = 4
        terraform_config.master_memory = 16 * MiB_UNITS

    @staticmethod
    def _configure_workers(terraform_config: BaseNodesConfig):
        terraform_config.masters_count = 0
        terraform_config.workers_count = 2
        terraform_config.worker_vcpu = 4
        terraform_config.worker_memory = 8 * MiB_UNITS
        terraform_config.ingress_dns = True
        terraform_config.cluster_name = global_variables.cluster_name

    @classmethod
    def _bind_all(cls, cluster_deployment: ClusterDeployment, agents: List[Agent]):
        for agent in agents:
            agent.bind(cluster_deployment)

    @classmethod
    def _unbind_all(cls, agents: List[Agent]):
        for agent in agents:
            agent.unbind()

    @classmethod
    def _get_vips(cls, nodes: Nodes):
        main_cidr = nodes.controller.get_primary_machine_cidr()

        # Arbitrarily choose 100 and 101 (e.g. 192.168.128.100 and 192.168.128.101) for the VIPs
        # Terraform/libvirt allocates IPs in the 2-90 range so these should be safe to use.
        # The configuration applied to the Terraform networks is stored in the following files
        # * terraform_files/limit_ip_dhcp_range.xsl
        api_vip = str(IPNetwork(main_cidr).ip + 100)
        ingress_vip = str(IPNetwork(main_cidr).ip + 101)

        return api_vip, ingress_vip

    @classmethod
    def _wait_for_install(
        cls, agent_cluster_install: AgentClusterInstall, agents: List[Agent], kubeconfig_path: Optional[str] = None
    ):
        agent_cluster_install.wait_to_be_ready(ready=True)
        agent_cluster_install.wait_to_be_installing()
        Agent.wait_for_agents_to_install(agents)
        agent_cluster_install.wait_to_be_installed()
        if kubeconfig_path:
            agent_cluster_install.download_kubeconfig(kubeconfig_path)

    @classmethod
    def _set_agent_cluster_install_machine_cidr(cls, agent_cluster_install: AgentClusterInstall, nodes: Nodes):
        machine_cidr = nodes.controller.get_primary_machine_cidr()
        agent_cluster_install.set_machine_networks([machine_cidr])

    @classmethod
    def download_iso_from_infra_env(cls, infra_env: InfraEnv, iso_download_path: str):
        log.info("getting iso download url")
        iso_download_url = infra_env.get_iso_download_url()
        log.info("downloading iso from url=%s", iso_download_url)
        utils.download_file(iso_download_url, iso_download_path, verify_ssl=False)
        assert os.path.isfile(iso_download_path)

    @classmethod
    def start_nodes(
        cls, nodes: Nodes, infra_env: InfraEnv, entity_config: BaseEntityConfig, is_static_ip: bool
    ) -> List[Agent]:
        infra_env.status()  # wait until install-env will have status (i.e until resource will be processed).
        cls.download_iso_from_infra_env(infra_env, entity_config.iso_download_path)

        log.info("iso downloaded, starting nodes")
        nodes.controller.log_configuration()
        log.info(f"Entity configuration {entity_config}")

        nodes.notify_iso_ready()
        nodes.start_all(check_ips=not (is_static_ip and entity_config.is_ipv6))

        log.info("waiting for host agent")
        agents = infra_env.wait_for_agents(len(nodes))
        node_list = nodes.controller.list_nodes()
        for agent in agents:
            agent.approve()
            cls._set_host_name_from_node(node_list, agent, entity_config.is_ipv4)

        return agents

    @classmethod
    def _set_host_name_from_node(cls, nodes: List[Node], agent: Agent, is_ipv4: bool) -> None:
        """
        Use the MAC address that is listed in the virt node object to find the interface entry
        in the host's inventory and take the host name from there
        The setting of the hostname is required for IPv6 only, because the nodes are booted with
        hostname equal to localhost which is neither unique not legal name for AI host
        """

        def find_matching_node_and_return_name():
            inventory = agent.status().get("inventory", {})
            for node in nodes:
                for mac_address in node.macs:
                    for interface in inventory.get("interfaces", []):
                        if interface["macAddress"].lower() == mac_address.lower():
                            return node.name

        hostname = waiting.wait(
            find_matching_node_and_return_name,
            timeout_seconds=60,
            sleep_seconds=1,
            waiting_for=f"agent={agent.ref} to find a hostname",
        )
        log.info(f"patching agent {agent.ref} with hostname {hostname}")
        agent.patch(hostname=hostname)

    @classmethod
    def deploy_image_set(cls, cluster_name: str, api_client: ApiClient):
        openshift_release_image = utils.get_openshift_release_image()
        image_set_name = f"{cluster_name}-image-set"
        image_set = ClusterImageSet(kube_api_client=api_client, name=image_set_name)
        image_set.create(openshift_release_image)

        return ClusterImageSetReference(image_set_name)

    @classmethod
    @JunitTestCase()
    def apply_static_network_config(
        cls,
        kube_api_context: KubeAPIContext,
        nodes: Nodes,
        cluster_name: str,
        infra_env_configuration: BaseInfraEnvConfig,
    ):
        static_network_config = static_network.generate_static_network_data_from_tf(
            nodes.controller.tf_folder, infra_env_configuration
        )

        mac_to_interface = static_network_config[0]["mac_interface_map"]
        interfaces = [
            {"name": item["logical_nic_name"], "macAddress": item["mac_address"]} for item in mac_to_interface
        ]

        nmstate_config = NMStateConfig(
            kube_api_client=kube_api_context.api_client,
            name=f"{cluster_name}-nmstate-config",
            namespace=kube_api_context.spoke_namespace,
        )
        nmstate_config.apply(
            config=yaml.safe_load(static_network_config[0]["network_yaml"]),
            interfaces=interfaces,
            label=cluster_name,
        )

        return static_network_config
