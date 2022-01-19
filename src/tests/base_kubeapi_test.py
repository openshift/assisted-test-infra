import os
from typing import List

import pytest
from kubernetes.client import ApiClient, CoreV1Api
from kubernetes.client.exceptions import ApiException as K8sApiException
from netaddr import IPNetwork

from assisted_test_infra.test_infra import BaseEntityConfig, Nodes, utils
from assisted_test_infra.test_infra.controllers import Node
from assisted_test_infra.test_infra.helper_classes.config import BaseNodeConfig
from assisted_test_infra.test_infra.helper_classes.kube_helpers import (
    Agent,
    AgentClusterInstall,
    ClusterDeployment,
    ClusterImageSet,
    ClusterImageSetReference,
    InfraEnv,
    KubeAPIContext,
)
from assisted_test_infra.test_infra.utils.kubeapi_utils import get_ip_for_single_node
from service_client import ClientFactory, log
from tests.base_test import BaseTest
from tests.config import ClusterConfig, global_variables


class BaseKubeAPI(BaseTest):
    @pytest.fixture(scope="session")
    def kube_api_client(self):
        yield ClientFactory.create_kube_api_client()

    @pytest.fixture()
    def kube_api_context(self, kube_api_client):
        kube_api_context = KubeAPIContext(kube_api_client, clean_on_exit=global_variables.test_teardown)

        with kube_api_context:
            v1 = CoreV1Api(kube_api_client)

            try:
                v1.create_namespace(
                    body={
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {
                            "name": global_variables.spoke_namespace,
                            "labels": {
                                "name": global_variables.spoke_namespace,
                            },
                        },
                    }
                )
            except K8sApiException as e:
                if e.status != 409:
                    raise

            yield kube_api_context

            if global_variables.test_teardown:
                v1.delete_namespace(global_variables.spoke_namespace)

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

    @staticmethod
    def _configure_single_node(terraform_config: BaseNodeConfig):
        terraform_config.masters_count = 1
        terraform_config.workers_count = 0
        terraform_config.master_vcpu = 8
        terraform_config.master_memory = 35840

    @staticmethod
    def _configure_highly_available(terraform_config: BaseNodeConfig):
        terraform_config.masters_count = 3
        terraform_config.workers_count = 0
        terraform_config.master_vcpu = 4
        terraform_config.master_memory = 17920

    @classmethod
    def _bind_all(cls, cluster_deployment: ClusterDeployment, agents: List[Agent]):
        for agent in agents:
            agent.bind(cluster_deployment)

    @classmethod
    def _get_vips(cls, cluster_config: ClusterConfig, nodes: Nodes):
        main_cidr = nodes.controller.get_primary_machine_cidr()

        # Arbitrarily choose 3, 4 (e.g. 192.168.128.3 and 192.168.128.4) for the VIPs
        # Terraform/libvirt allocates IPs in the 10+ range so these should be safe to use
        # TODO: Find a more robust solution to choose the VIPs. KubeAPI Assisted does not do
        #  DHCP for VIPs.
        api_vip = str(IPNetwork(main_cidr).ip + 3)
        ingress_vip = str(IPNetwork(main_cidr).ip + 4)

        return api_vip, ingress_vip

    @classmethod
    def _wait_for_install(cls, agent_cluster_install: AgentClusterInstall, agents: List[Agent]):
        agent_cluster_install.wait_to_be_ready(ready=True)
        agent_cluster_install.wait_to_be_installing()
        Agent.wait_for_agents_to_install(agents)
        agent_cluster_install.wait_to_be_installed()

    @classmethod
    def _set_agent_cluster_install_machine_cidr(cls, agent_cluster_install: AgentClusterInstall, nodes: Nodes):
        machine_cidr = nodes.controller.get_primary_machine_cidr()
        agent_cluster_install.set_machinenetwork(machine_cidr)

    @classmethod
    def download_iso_from_infra_env(cls, infra_env: InfraEnv, iso_download_path: str):
        log.info("getting iso download url")
        iso_download_url = infra_env.get_iso_download_url()
        log.info("downloading iso from url=%s", iso_download_url)
        utils.download_iso(iso_download_url, iso_download_path)
        assert os.path.isfile(iso_download_path)

    @classmethod
    def start_nodes(cls, nodes: Nodes, infra_env: InfraEnv, entity_config: BaseEntityConfig, is_ipv4) -> List[Agent]:
        infra_env.status()  # wait until install-env will have status (i.e until resource will be processed).
        cls.download_iso_from_infra_env(infra_env, entity_config.iso_download_path)

        log.info("iso downloaded, starting nodes")
        nodes.start_all()

        log.info("waiting for host agent")
        agents = infra_env.wait_for_agents(len(nodes))
        for agent in agents:
            agent.approve()
            cls.set_agent_hostname(nodes[0], agent, is_ipv4)  # Currently only supports single node

        return agents

    @classmethod
    def set_agent_hostname(cls, node: Node, agent: Agent, is_ipv4: bool) -> None:
        if is_ipv4:
            return
        log.info("patching agent hostname=%s", node)
        agent.patch(hostname=node.name)

    @classmethod
    def set_single_node_ip(cls, cluster_deployment: ClusterDeployment, nodes: Nodes, is_ipv4: bool):
        log.info("waiting to have host single node ip")
        single_node_ip = get_ip_for_single_node(cluster_deployment, is_ipv4)
        nodes.controller.tf.change_variables(
            {
                "single_node_ip": single_node_ip,
                "bootstrap_in_place": True,
            }
        )
        log.info("single node ip=%s", single_node_ip)

    @classmethod
    def deploy_image_set(cls, cluster_name: str, api_client: ApiClient):
        openshift_release_image = utils.get_openshift_release_image()
        image_set_name = f"{cluster_name}-image-set"
        image_set = ClusterImageSet(kube_api_client=api_client, name=image_set_name)
        image_set.create(openshift_release_image)

        return ClusterImageSetReference(image_set_name)
