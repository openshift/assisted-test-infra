import json
import subprocess
import uuid
from typing import Any

import waiting
from junit_report import JunitTestCase

import consts
from assisted_test_infra.test_infra import BaseInfraEnvConfig, utils
from assisted_test_infra.test_infra.helper_classes.base_cluster import BaseCluster
from assisted_test_infra.test_infra.helper_classes.config.base_day2_cluster_config import BaseDay2ClusterConfig
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from assisted_test_infra.test_infra.utils.waiting import wait_till_all_hosts_are_in_status
from service_client import log
from service_client.assisted_service_api import InventoryClient


class Day2Cluster(BaseCluster):
    _config: BaseDay2ClusterConfig

    def __init__(
        self,
        api_client: InventoryClient,
        config: BaseDay2ClusterConfig,
        infra_env_config: BaseInfraEnvConfig,
        day2_nodes: Nodes,
    ):
        self._kubeconfig_path = utils.get_kubeconfig_path(config.day1_cluster.name)
        self.name = config.cluster_name.get()

        super().__init__(api_client, config, infra_env_config, day2_nodes)

    def _create(self) -> str:
        openshift_cluster_id = str(uuid.uuid4())
        params = {
            "openshift_version": self._config.openshift_version,
            "api_vip_dnsname": self._config.day1_api_vip_dnsname,
        }

        cluster = self.api_client.create_day2_cluster(self.name, openshift_cluster_id, **params)

        self._config.cluster_id = cluster.id
        return cluster.id

    def update_existing(self) -> str:
        raise NotImplementedError("Creating Day2Cluster object from an existing cluster is not implemented.")

    def prepare_for_installation(self):
        """Prepare the day2 worker nodes. When this method finishes, the hosts are in 'known' status."""

        self.set_pull_secret(self._config.pull_secret)
        self.set_cluster_proxy()
        self.config_etc_hosts(self._config.day1_cluster_details.api_vip, self._config.day1_api_vip_dnsname)

        # spawn VMs
        super(Day2Cluster, self).prepare_for_installation(
            is_static_ip=self._config.day1_cluster._infra_env_config.is_static_ip
        )
        self.nodes.wait_for_networking()
        self.set_hostnames_and_roles()

        # wait for host to be known
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self._config.cluster_id,
            nodes_count=self._config.day2_workers_count,
            statuses=[consts.NodesStatus.KNOWN],
            interval=30,
        )

    def set_cluster_proxy(self):
        """
        Set cluster proxy - copy proxy configuration from another (e.g. day 1) cluster,
        or allow setting/overriding it via command arguments
        """
        if self._config.proxy:
            http_proxy = self._config.proxy.http_proxy
            https_proxy = self._config.proxy.https_proxy
            no_proxy = self._config.proxy.no_proxy
            self.api_client.set_cluster_proxy(self.id, http_proxy, https_proxy, no_proxy)

    @staticmethod
    def config_etc_hosts(api_vip: str, api_vip_dnsname: str):
        with open("/etc/hosts", "r") as f:
            hosts_lines = f.readlines()
        for i, line in enumerate(hosts_lines):
            if api_vip_dnsname in line:
                hosts_lines[i] = api_vip + " " + api_vip_dnsname + "\n"
                break
        else:
            hosts_lines.append(api_vip + " " + api_vip_dnsname + "\n")
        with open("/etc/hosts", "w") as f:
            f.writelines(hosts_lines)

    @JunitTestCase()
    def start_install_and_wait_for_installed(self):
        ocp_ready_nodes = self.get_ocp_cluster_ready_nodes_num()
        self._install_day2_cluster()
        self.wait_nodes_to_be_in_ocp(ocp_ready_nodes)

    def wait_nodes_to_be_in_ocp(self, ocp_ready_nodes):
        def wait_nodes_join_ocp_cluster(num_orig_nodes: int, num_new_nodes: int) -> bool:
            self.approve_workers_on_ocp_cluster()
            return self.get_ocp_cluster_ready_nodes_num() == num_orig_nodes + num_new_nodes

        log.info("Waiting until installed nodes has actually been added to the OCP cluster")
        waiting.wait(
            lambda: wait_nodes_join_ocp_cluster(ocp_ready_nodes, self._config.day2_workers_count),
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
            sleep_seconds=30,
            waiting_for="Day2 nodes to be added to OCP cluster",
            expected_exceptions=Exception,
        )
        log.info(f"{self._config.day2_workers_count} worker nodes were successfully added to OCP cluster")

    def approve_workers_on_ocp_cluster(self):
        csrs = self.get_ocp_cluster_csrs(self._kubeconfig_path)
        for csr in csrs:
            if not csr["status"]:
                csr_name = csr["metadata"]["name"]
                subprocess.check_output(
                    f"oc --kubeconfig={self._kubeconfig_path} adm certificate approve {csr_name}",
                    shell=True,
                )
                log.info("CSR %s for node %s has been approved", csr_name, csr["spec"]["username"])

    @staticmethod
    def get_ocp_cluster_csrs(kubeconfig: Any) -> Any:
        res = subprocess.check_output(f"oc --kubeconfig={kubeconfig} get csr --output=json", shell=True)
        return json.loads(res)["items"]

    def _install_day2_cluster(self):
        # Start day2 nodes installation
        log.info(f"Start installing all known nodes in the cluster {self.id}")
        hosts = self.api_client.get_cluster_hosts(self.id)

        for host in hosts:
            if host["status"] == "known":
                self.api_client.install_day2_host(self._infra_env_config.infra_env_id, host["id"])

        log.info(
            f"Waiting until all nodes of cluster {self.id} have been installed (reached " "added-to-existing-cluster)",
        )

        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=self._config.day2_workers_count,
            statuses=[consts.NodesStatus.DAY2_INSTALLED],
            interval=30,
        )

    def get_ocp_cluster_ready_nodes_num(self) -> int:
        nodes = self.get_ocp_cluster_nodes(self._kubeconfig_path)
        return len([node for node in nodes if self.is_ocp_node_ready(node["status"])])

    @staticmethod
    def get_ocp_cluster_nodes(kubeconfig: str):
        res = subprocess.check_output(f"oc --kubeconfig={kubeconfig} get nodes --output=json", shell=True)
        return json.loads(res)["items"]

    @staticmethod
    def is_ocp_node_ready(node_status: any) -> bool:
        if not node_status:
            return False
        for condition in node_status["conditions"]:
            if condition["status"] == "True" and condition["type"] == "Ready":
                return True
        return False
