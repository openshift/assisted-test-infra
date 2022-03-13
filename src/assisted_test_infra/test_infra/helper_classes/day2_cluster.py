import ipaddress
import json
import os
import subprocess
import time
import uuid
from abc import ABC
from typing import Any

import waiting

import consts
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from assisted_test_infra.test_infra.helper_classes.config.day2_cluster_config import BaseDay2ClusterConfig
from assisted_test_infra.test_infra.tools import static_network
from assisted_test_infra.test_infra.utils.waiting import wait_till_all_hosts_are_in_status
from service_client import log
from service_client.assisted_service_api import InventoryClient
from tests.config import ClusterConfig, TerraformConfig


class Day2Cluster(ABC):
    def __init__(self, api_client: InventoryClient, config: BaseDay2ClusterConfig):
        self.config = config
        self.api_client = api_client

    def prepare_for_installation(self):
        utils.recreate_folder(consts.IMAGE_FOLDER, force_recreate=False)

        cluster = self.api_client.cluster_get(cluster_id=self.config.day1_cluster_id)
        self.config.day1_cluster_name = cluster.name
        openshift_version = cluster.openshift_version
        api_vip_dnsname = "api." + self.config.day1_cluster_name + "." + cluster.base_dns_domain
        api_vip_ip = cluster.api_vip

        openshift_cluster_id = str(uuid.uuid4())
        params = {"openshift_version": openshift_version, "api_vip_dnsname": api_vip_dnsname}
        cluster = self.api_client.create_day2_cluster(
            self.config.day1_cluster_name + "-day2", openshift_cluster_id, **params
        )
        self.config.cluster_id = cluster.id
        self.api_client.set_pull_secret(cluster.id, self.config.pull_secret)
        self.set_cluster_proxy(cluster.id)

        self.config_etc_hosts(api_vip_ip, api_vip_dnsname)

        self.config.tf_folder = os.path.join(
            utils.TerraformControllerUtil.get_folder(self.config.day1_cluster_name), consts.Platforms.BARE_METAL
        )
        self.configure_terraform(self.config.tf_folder, self.config.day2_workers_count, api_vip_ip)

        static_network_config = None
        if self.config.is_static_ip:
            static_network_config = static_network.generate_day2_static_network_data_from_tf(
                self.config.tf_folder, self.config.day2_workers_count
            )

        # Generate image
        infra_env = self.api_client.create_infra_env(
            cluster_id=cluster.id,
            name=self.config.day1_cluster_name + "_infra-env",
            ssh_public_key=self.config.ssh_public_key,
            static_network_config=static_network_config,
            pull_secret=self.config.pull_secret,
            openshift_version=openshift_version,
        )
        self.config.infra_env_id = infra_env.id
        # Download image
        iso_download_url = infra_env.download_url
        image_path = os.path.join(consts.IMAGE_FOLDER, f"{self.config.day1_cluster_name}-installer-image.iso")
        log.info(f"Downloading image {iso_download_url} to {image_path}")
        utils.download_file(iso_download_url, image_path, False)

    def start_install_and_wait_for_installed(self):
        cluster_name = self.config.day1_cluster_name
        # Running twice as a workaround for an issue with terraform not spawning a new node on first apply.
        for _ in range(2):
            with utils.file_lock_context():
                utils.run_command(
                    f"make _apply_terraform CLUSTER_NAME={cluster_name} PLATFORM={consts.Platforms.BARE_METAL}"
                )
        time.sleep(5)

        num_nodes_to_wait = self.config.day2_workers_count
        installed_status = consts.NodesStatus.DAY2_INSTALLED

        tfvars = utils.get_tfvars(self.config.tf_folder)
        tf_network_name = tfvars["libvirt_network_name"]

        config = TerraformConfig()
        config.nodes_count = num_nodes_to_wait
        libvirt_controller = LibvirtController(config=config, entity_config=ClusterConfig())
        libvirt_controller.wait_till_nodes_are_ready(network_name=tf_network_name)

        # Wait for day2 nodes
        waiting.wait(
            lambda: self.are_libvirt_nodes_in_cluster_hosts(),
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
            sleep_seconds=10,
            waiting_for="Nodes to be registered in inventory service",
        )
        self.set_nodes_hostnames_if_needed(tf_network_name)
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.config.cluster_id,
            nodes_count=self.config.day2_workers_count,
            statuses=[consts.NodesStatus.KNOWN],
            interval=30,
        )

        # Start day2 nodes installation
        log.info("Start installing all known nodes in the cluster %s", self.config.cluster_id)
        kubeconfig = utils.get_kubeconfig_path(self.config.day1_cluster_name)
        ocp_ready_nodes = self.get_ocp_cluster_ready_nodes_num(kubeconfig)
        hosts = self.api_client.get_cluster_hosts(self.config.cluster_id)
        [
            self.api_client.install_day2_host(self.config.infra_env_id, host["id"])
            for host in hosts
            if host["status"] == "known"
        ]

        log.info(
            "Waiting until all nodes of cluster %s have been installed (reached added-to-existing-cluster)",
            self.config.cluster_id,
        )
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.config.cluster_id,
            nodes_count=num_nodes_to_wait,
            statuses=[installed_status],
            interval=30,
        )

        log.info("Waiting until installed nodes has actually been added to the OCP cluster")
        waiting.wait(
            lambda: self.wait_nodes_join_ocp_cluster(ocp_ready_nodes, self.config.day2_workers_count, kubeconfig),
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
            sleep_seconds=30,
            waiting_for="Day2 nodes to be added to OCP cluster",
            expected_exceptions=Exception,
        )
        log.info("%d worker nodes were successfully added to OCP cluster", self.config.day2_workers_count)

    def set_cluster_proxy(self, cluster_id: str):
        """
        Set cluster proxy - copy proxy configuration from another (e.g. day 1) cluster,
        or allow setting/overriding it via command arguments
        """
        if self.config.proxy:
            http_proxy = self.config.proxy.http_proxy
            https_proxy = self.config.proxy.https_proxy
            no_proxy = self.config.proxy.no_proxy
            self.api_client.set_cluster_proxy(cluster_id, http_proxy, https_proxy, no_proxy)

    def config_etc_hosts(self, api_vip_ip: str, api_vip_dnsname: str):
        with open("/etc/hosts", "r") as f:
            hosts_lines = f.readlines()
        for i, line in enumerate(hosts_lines):
            if api_vip_dnsname in line:
                hosts_lines[i] = api_vip_ip + " " + api_vip_dnsname + "\n"
                break
        else:
            hosts_lines.append(api_vip_ip + " " + api_vip_dnsname + "\n")
        with open("/etc/hosts", "w") as f:
            f.writelines(hosts_lines)

    def configure_terraform(self, tf_folder: str, num_worker_nodes: int, api_vip_ip: str):
        tfvars = utils.get_tfvars(tf_folder)
        self.configure_terraform_workers_nodes(tfvars, num_worker_nodes)
        tfvars["api_vip"] = api_vip_ip
        utils.set_tfvars(tf_folder, tfvars)

    def configure_terraform_workers_nodes(self, tfvars: Any, num_worker_nodes: int):
        num_workers = tfvars["worker_count"] + num_worker_nodes
        tfvars["worker_count"] = num_workers
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

    def set_workers_addresses_by_type(
        self, tfvars: Any, num_worker_nodes: int, master_ip_type: str, worker_ip_type: str, worker_mac_type: str
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

    def get_ocp_cluster_nodes(self, kubeconfig: str):
        res = subprocess.check_output(f"oc --kubeconfig={kubeconfig} get nodes --output=json", shell=True)
        return json.loads(res)["items"]

    def is_ocp_node_ready(self, node_status: any) -> bool:
        if not node_status:
            return False
        for condition in node_status["conditions"]:
            if condition["status"] == "True" and condition["type"] == "Ready":
                return True
        return False

    def are_libvirt_nodes_in_cluster_hosts(self) -> bool:
        try:
            hosts_macs = self.api_client.get_hosts_id_with_macs(self.config.cluster_id)
        except BaseException:
            log.error("Failed to get nodes macs for cluster: %s", self.config.cluster_id)
            return False
        num_macs = len([mac for mac in hosts_macs if mac != ""])
        return num_macs >= self.config.day2_workers_count

    def set_nodes_hostnames_if_needed(self, network_name: str):
        if self.config.is_ipv6 or self.config.is_static_ip:
            tf = utils.TerraformUtils(working_dir=self.config.tf_folder)
            libvirt_nodes = utils.extract_nodes_from_tf_state(tf.get_state(), network_name, consts.NodeRoles.WORKER)
            log.info(
                "Set hostnames of day2 cluster %s in case of static network configuration or "
                "to work around libvirt for Terrafrom not setting hostnames of IPv6 hosts",
                self.config.cluster_id,
            )
            self.update_hosts(self.api_client, self.config.cluster_id, libvirt_nodes)

    def update_hosts(self, client: InventoryClient, cluster_id: str, libvirt_nodes: dict):
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

    def wait_nodes_join_ocp_cluster(self, num_orig_nodes: int, num_new_nodes: int, kubeconfig: Any) -> bool:
        self.approve_workers_on_ocp_cluster(kubeconfig)
        return self.get_ocp_cluster_ready_nodes_num(kubeconfig) == num_orig_nodes + num_new_nodes

    def get_ocp_cluster_ready_nodes_num(self, kubeconfig: Any) -> int:
        nodes = self.get_ocp_cluster_nodes(kubeconfig)
        return len([node for node in nodes if self.is_ocp_node_ready(node["status"])])

    def approve_workers_on_ocp_cluster(self, kubeconfig: Any):
        csrs = self.get_ocp_cluster_csrs(kubeconfig)
        for csr in csrs:
            if not csr["status"]:
                csr_name = csr["metadata"]["name"]
                subprocess.check_output(f"oc --kubeconfig={kubeconfig} adm certificate approve {csr_name}", shell=True)
                log.info("CSR %s for node %s has been approved", csr_name, csr["spec"]["username"])

    def get_ocp_cluster_csrs(self, kubeconfig: Any) -> Any:
        res = subprocess.check_output(f"oc --kubeconfig={kubeconfig} get csr --output=json", shell=True)
        return json.loads(res)["items"]
