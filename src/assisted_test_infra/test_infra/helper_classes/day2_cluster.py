import ipaddress
import json
import os
import subprocess
import time
import uuid
from typing import Any

import waiting
from junit_report import JunitTestCase

import consts
from assisted_test_infra.test_infra import BaseInfraEnvConfig, ClusterName, utils
from assisted_test_infra.test_infra.helper_classes.base_cluster import BaseCluster
from assisted_test_infra.test_infra.controllers import NodeController
from assisted_test_infra.test_infra.helper_classes.cluster import Cluster
from assisted_test_infra.test_infra.helper_classes.config.base_day2_cluster_config import BaseDay2ClusterConfig
from assisted_test_infra.test_infra.tools import static_network
from assisted_test_infra.test_infra.utils.waiting import wait_till_all_hosts_are_in_status
from service_client import log
from service_client.assisted_service_api import InventoryClient


class Day2Cluster(BaseCluster):
    _config: BaseDay2ClusterConfig

    def __init__(self, config: BaseDay2ClusterConfig, infra_env_config: BaseInfraEnvConfig, cluster: Cluster):
        self._day1_cluster: Cluster = cluster
        self._api_vip = None

        super().__init__(self._day1_cluster.api_client, config, infra_env_config, self._day1_cluster.nodes)

    def wait_until_hosts_are_discovered(self, allow_insufficient=False, nodes_count: int = None):
        statuses = [consts.NodesStatus.PENDING_FOR_INPUT, consts.NodesStatus.KNOWN]
        if allow_insufficient:
            statuses.append(consts.NodesStatus.INSUFFICIENT)
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count or self.nodes.nodes_count,
            statuses=statuses,
            timeout=consts.NODES_REGISTERED_TIMEOUT,
        )

    def _create(self) -> str:
        if not self._day1_cluster.is_installed:
            self._day1_cluster.prepare_for_installation()
            self._day1_cluster.start_install_and_wait_for_installed()

        openshift_cluster_id = str(uuid.uuid4())
        day1_cluster = self._day1_cluster.get_details()

        self._api_vip = day1_cluster.api_vip
        api_vip_dnsname = "api." + self._day1_cluster.name + "." + day1_cluster.base_dns_domain
        self._config.day1_cluster_name = day1_cluster.name
        params = {"openshift_version": self._config.openshift_version, "api_vip_dnsname": api_vip_dnsname}
        cluster = self.api_client.create_day2_cluster(self._day1_cluster.name + "-day2", openshift_cluster_id, **params)
        self._config.cluster_id = cluster.id

        self._config.cluster_name = ClusterName(
            prefix=self._day1_cluster._config.cluster_name.prefix,
            suffix=self._day1_cluster._config.cluster_name.suffix + cluster.name.replace(day1_cluster.name, ""),
        )

        return cluster.id

    def update_existing(self) -> str:
        return self._create()

    def prepare_for_installation(self):
        self._config.day1_cluster_id = self._day1_cluster.id

        day2_cluster = self.get_details()
        self._config.cluster_id = day2_cluster.id
        self._day1_cluster.set_pull_secret(self._config.pull_secret, cluster_id=day2_cluster.id)
        self.set_cluster_proxy(day2_cluster.id)
        self.config_etc_hosts(self._api_vip, day2_cluster.api_vip_dns_name)

        self.nodes.controller.tf_folder = os.path.join(
            utils.TerraformControllerUtil.get_folder(self._day1_cluster.name), consts.Platforms.BARE_METAL
        )
        self.configure_terraform()
        self._day1_cluster.download_image()

        static_network_config = None
        if self._day1_cluster._infra_env_config.is_static_ip:
            static_network_config = self.nodes.controller.get_day2_static_network_data()

        tfvars = utils.get_tfvars(self.nodes.controller.tf_folder)
        self.download_image(
            iso_download_path=tfvars["worker_image_path"],
            static_network_config=static_network_config,
        )

    def set_cluster_proxy(self, cluster_id: str):
        """
        Set cluster proxy - copy proxy configuration from another (e.g. day 1) cluster,
        or allow setting/overriding it via command arguments
        """
        if self._config.proxy:
            http_proxy = self._config.proxy.http_proxy
            https_proxy = self._config.proxy.https_proxy
            no_proxy = self._config.proxy.no_proxy
            self.api_client.set_cluster_proxy(cluster_id, http_proxy, https_proxy, no_proxy)

    @classmethod
    def config_etc_hosts(cls, api_vip: str, api_vip_dnsname: str):
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

    def configure_terraform(self):
        """Use same terraform as the one used to spawn the day1 cluster, update the variables accordingly in order to spawn the day2 worker nodes"""
        tfvars = utils.get_tfvars(self.nodes.controller.tf_folder)
        self.configure_terraform_workers_nodes(tfvars)
        tfvars["api_vip"] = self._api_vip
        tfvars["running"] = True
        utils.set_tfvars(self.nodes.controller.tf_folder, tfvars)

    def configure_terraform_workers_nodes(self, tfvars: Any):
        num_worker_nodes = self._config.day2_workers_count
        tfvars["worker_count"] = tfvars["worker_count"] + num_worker_nodes
        self.set_workers_addresses_by_type(
            tfvars, num_worker_nodes, "libvirt_master_ips", "libvirt_worker_ips", "libvirt_worker_macs"
        )
        self.set_workers_addresses_by_type(
            tfvars,
            num_worker_nodes,
            "libvirt_secondary_master_ips",
            "libvirt_secondary_worker_ips",
            "libvirt_secondary_worker_macs",
        )

    @classmethod
    def set_workers_addresses_by_type(
        cls, tfvars: Any, num_worker_nodes: int, master_ip_type: str, worker_ip_type: str, worker_mac_type: str
    ):

        old_worker_ips_list = tfvars[worker_ip_type]
        last_master_addresses = tfvars[master_ip_type][-1]

        if last_master_addresses:
            if old_worker_ips_list:
                worker_starting_ip = ipaddress.ip_address(old_worker_ips_list[-1][0])
            else:
                worker_starting_ip = ipaddress.ip_address(last_master_addresses[0])

            worker_ips_list = old_worker_ips_list + utils.create_ip_address_nested_list(
                num_worker_nodes, worker_starting_ip + 1
            )
        else:
            log.info(
                "IPv6-only environment. IP addresses are left empty and will be allocated by libvirt "
                "DHCP because of a bug in Terraform plugin"
            )
            worker_ips_list = old_worker_ips_list + utils.create_empty_nested_list(num_worker_nodes)

        tfvars[worker_ip_type] = worker_ips_list

        old_worker_mac_addresses = tfvars[worker_mac_type]
        tfvars[worker_mac_type] = old_worker_mac_addresses + static_network.generate_macs(num_worker_nodes)

    def wait_for_day2_nodes(self):
        def are_libvirt_nodes_in_cluster_hosts() -> bool:
            try:
                hosts = self.api_client.get_cluster_hosts(self.id)
            except BaseException:
                log.exception(f"Failed to get cluster hosts: {self.id}")
                return False
            return len(hosts) >= self._config.day2_workers_count

        waiting.wait(
            lambda: are_libvirt_nodes_in_cluster_hosts(),
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
            sleep_seconds=10,
            waiting_for="Nodes to be registered in inventory service",
        )

    def set_nodes_hostnames_if_needed(self):
        if self._config.is_ipv6 or self._day1_cluster._infra_env_config.is_static_ip:
            tf_state = self.nodes.controller.tf.get_state()
            network_name = self.nodes.controller.network_name
            libvirt_nodes = utils.extract_nodes_from_tf_state(tf_state, network_name, consts.NodeRoles.WORKER)
            log.info(
                f"Set hostnames of day2 cluster {self.id} in case of static network configuration or "
                "to work around libvirt for Terrafrom not setting hostnames of IPv6 hosts",
            )
            self.update_hosts(self.api_client, self.id, libvirt_nodes)

    @classmethod
    def update_hosts(cls, client: InventoryClient, cluster_id: str, libvirt_nodes: dict):
        """
        Update names of the hosts in a cluster from a dictionary of libvirt nodes.

        An entry from the dictionary is matched to a host by the host's MAC address (of any NIC).
        Entries that do not match any host in the cluster are ignored.

        Args:
            client: An assisted service client
            cluster_id: ID of the cluster to update
            libvirt_nodes: A dictionary that may contain data about cluster hosts
        """
        inventory_hosts = client.get_cluster_hosts(cluster_id)

        for libvirt_mac, libvirt_metadata in libvirt_nodes.items():
            for host in inventory_hosts:
                inventory = json.loads(host["inventory"])

                if libvirt_mac.lower() in map(
                    lambda interface: interface["mac_address"].lower(),
                    inventory["interfaces"],
                ):
                    client.update_host(
                        infra_env_id=host["infra_env_id"], host_id=host["id"], host_name=libvirt_metadata["name"]
                    )

    @JunitTestCase()
    def start_install_and_wait_for_installed(self):
        # Running twice as a workaround for an issue with terraform not spawning a new node on first apply.
        for _ in range(2):
            with utils.file_lock_context():
                res = utils.run_command(
                    f"make _apply_terraform CLUSTER_NAME={self._day1_cluster.name} "
                    f"PLATFORM={consts.Platforms.BARE_METAL}"
                )
                log.info(res[0])
        time.sleep(5)

        num_nodes_to_wait = self._config.day2_workers_count
        installed_status = consts.NodesStatus.DAY2_INSTALLED

        # make sure we use the same network as defined in the terraform stack
        tfvars = utils.get_tfvars(self.nodes.controller.tf_folder)
        self.nodes.wait_till_nodes_are_ready(network_name=tfvars["libvirt_network_name"])

        self.wait_for_day2_nodes()
        self.set_nodes_hostnames_if_needed()

        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self._config.cluster_id,
            nodes_count=self._config.day2_workers_count,
            statuses=[consts.NodesStatus.KNOWN],
            interval=30,
        )

        ocp_ready_nodes = self.get_ocp_cluster_ready_nodes_num()
        self._install_day2_cluster(num_nodes_to_wait, installed_status)
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
        csrs = self.get_ocp_cluster_csrs(self._day1_cluster.kubeconfig_path)
        for csr in csrs:
            if not csr["status"]:
                csr_name = csr["metadata"]["name"]
                subprocess.check_output(
                    f"oc --kubeconfig={self._day1_cluster.kubeconfig_path} adm certificate approve {csr_name}",
                    shell=True,
                )
                log.info("CSR %s for node %s has been approved", csr_name, csr["spec"]["username"])

    @classmethod
    def get_ocp_cluster_csrs(cls, kubeconfig: Any) -> Any:
        res = subprocess.check_output(f"oc --kubeconfig={kubeconfig} get csr --output=json", shell=True)
        return json.loads(res)["items"]

    def _install_day2_cluster(self, num_nodes_to_wait: int, installed_status: str):
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
            nodes_count=num_nodes_to_wait,
            statuses=[installed_status],
            interval=30,
        )

    def get_ocp_cluster_ready_nodes_num(self) -> int:
        kubeconfig = utils.get_kubeconfig_path(self._config.day1_cluster_name)
        nodes = self.get_ocp_cluster_nodes(kubeconfig)
        return len([node for node in nodes if self.is_ocp_node_ready(node["status"])])

    @classmethod
    def get_ocp_cluster_nodes(cls, kubeconfig: str):
        res = subprocess.check_output(f"oc --kubeconfig={kubeconfig} get nodes --output=json", shell=True)
        return json.loads(res)["items"]

    @classmethod
    def is_ocp_node_ready(cls, node_status: any) -> bool:
        if not node_status:
            return False
        for condition in node_status["conditions"]:
            if condition["status"] == "True" and condition["type"] == "Ready":
                return True
        return False
