import json
import random
from typing import Dict, Iterator, List, Optional

import waiting
from munch import Munch
from paramiko import SSHException
from scp import SCPException

import consts
from assisted_test_infra.test_infra.controllers.node_controllers import Node
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.tools import run_concurrently
from service_client.logger import SuppressAndLog, log


class NodeMapping:
    def __init__(self, node, cluster_host):
        self.name = node.name
        self.node = node
        self.cluster_host = cluster_host

class Nodes:
    DEFAULT_STATIC_IPS_CONFIG = False

    def __init__(self, node_controller: NodeController):
        self.controller = node_controller
        self._nodes = None
        self._nodes_as_dict = None
        self.__is_prepared = False

    @property
    def is_prepared(self) -> bool:
        return self.__is_prepared

    @property
    def masters_count(self):
        return self.controller.masters_count

    @property
    def workers_count(self):
        return self.controller.workers_count

    @property
    def nodes_count(self):
        return self.workers_count + self.masters_count

    @property
    def nodes(self) -> List[Node]:
        if not self._nodes:
            self._nodes = self.controller.list_nodes()
        return self._nodes

    @property
    def is_ipv4(self):
        return self.controller.is_ipv4

    @property
    def is_ipv6(self):
        return self.controller.is_ipv6

    def __getitem__(self, i):
        return self.nodes[i]

    def __len__(self):
        return len(self.nodes)

    def __iter__(self) -> Iterator[Node]:
        for n in self.nodes:
            yield n

    def drop_cache(self):
        self._nodes = None
        self._nodes_as_dict = None

    def get_nodes(self, refresh=False) -> List[Node]:
        if refresh:
            self.drop_cache()

        return self.nodes

    def get_masters(self):
        return [node for node in self.nodes if node.is_master_in_name()]

    def get_workers(self):
        return [node for node in self.nodes if node.is_worker_in_name()]

    @property
    def nodes_as_dict(self):
        if not self._nodes_as_dict:
            self._nodes_as_dict = {node.name: node for node in self.nodes}
        return self._nodes_as_dict

    @property
    def setup_time(self):
        return self.controller.setup_time

    def get_random_node(self):
        return random.choice(self.nodes)

    def shutdown_all(self):
        self.run_for_all_nodes("shutdown")
        self.drop_cache()

    def notify_iso_ready(self):
        self.controller.notify_iso_ready()

    def start_all(self, check_ips=True):
        self.run_for_all_nodes("start", check_ips)

    def start_given(self, nodes):
        self.run_for_given_nodes(nodes, "start")
        self.drop_cache()

    def shutdown_given(self, nodes):
        self.run_for_given_nodes(nodes, "shutdown")
        self.drop_cache()

    def format_all_disks(self):
        self.run_for_all_nodes("format_disk")

    def destroy_all(self):
        self.run_for_all_nodes("shutdown")

    def destroy_all_nodes(self):
        self.controller.destroy_all_nodes()
        self.__is_prepared = False

    def prepare_nodes(self):
        if not self.__is_prepared:
            self.controller.prepare_nodes()
            self.__is_prepared = True

    def reboot_all(self):
        self.run_for_all_nodes("restart")
        self.drop_cache()

    def reboot_given(self, nodes):
        self.run_for_given_nodes(nodes, "restart")
        self.drop_cache()

    def get_cluster_network(self):
        return self.controller.get_cluster_network()

    def set_correct_boot_order(self, nodes=None, start_nodes=False):
        nodes = nodes or self.nodes
        log.info("Going to set correct boot order to nodes: %s", nodes)
        self.run_for_given_nodes(nodes, "set_boot_order_flow", False, start_nodes)

    def run_for_all_nodes(self, func_name, *args):
        return self.run_for_given_nodes(self.nodes, func_name, *args)

    def run_for_given_nodes(self, nodes, func_name, *args):
        log.info("Running <%s> on nodes: %s", func_name, [node.name for node in nodes])
        if self.controller._config.tf_platform == consts.Platforms.NUTANIX:
            # nutanix doesn't allow concurrent requests
            res = []
            for node in nodes:
                res.append(getattr(node, func_name)(*args))
            return res

        return run_concurrently([(getattr(node, func_name), *args) for node in nodes])

    def run_for_given_nodes_by_cluster_hosts(self, cluster_hosts, func_name, *args):
        return self.run_for_given_nodes(
            [self.get_node_from_cluster_host(host) for host in cluster_hosts], func_name, *args
        )

    @staticmethod
    def run_ssh_command_on_given_nodes(nodes, command) -> Dict:
        return run_concurrently({node.name: (node.run_command, command) for node in nodes})

    def set_wrong_boot_order(self, nodes=None, start_nodes=True):
        nodes = nodes or self.nodes
        log.info("Setting wrong boot order for %s", self.nodes_as_dict.keys())
        self.run_for_given_nodes(nodes, "set_boot_order_flow", True, start_nodes)

    def get_bootstrap_node(self, cluster) -> Node:
        for cluster_host_object in cluster.get_hosts():
            if cluster_host_object.get("bootstrap", False):
                node = self.get_node_from_cluster_host(cluster_host_object)
                log.info("Bootstrap node is %s", node.name)
                return node

    def create_nodes_cluster_hosts_mapping(self, cluster):
        node_mapping_dict = {}
        for cluster_host_object in cluster.get_hosts():
            name = self.get_cluster_hostname(cluster_host_object)
            node_mapping_dict[name] = NodeMapping(self.nodes_as_dict[name], Munch.fromDict(cluster_host_object))
        return node_mapping_dict

    def get_node_from_cluster_host(self, cluster_host_object):
        hostname = self.get_cluster_hostname(cluster_host_object)
        return self.get_node_by_hostname(hostname)

    def get_node_by_hostname(self, get_node_by_hostname):
        return self.nodes_as_dict[get_node_by_hostname]

    def get_cluster_host_obj_from_node(self, cluster, node):
        mapping = self.create_nodes_cluster_hosts_mapping(cluster=cluster)
        return mapping[node.name].cluster_host

    @staticmethod
    def get_cluster_hostname(cluster_host_object):
        inventory = json.loads(cluster_host_object["inventory"])
        return inventory["hostname"]

    def set_single_node_ip(self, ip):
        self.controller.set_single_node_ip(ip)

    def wait_for_networking(
        self,
        timeout=3 * consts.MINUTE,
        interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
    ):
        log.info("Wait till %s nodes have MAC and IP address", len(self.nodes))

        # Best effort
        with SuppressAndLog(waiting.TimeoutExpired):
            waiting.wait(
                lambda: self._are_nodes_network_prepared(),
                timeout_seconds=timeout,
                sleep_seconds=interval,
                waiting_for="nodes to have IP and MAC addresses",
            )

    def _are_nodes_network_prepared(self):
        return all(node.macs and node.ips for node in self.nodes)

    def wait_till_nodes_are_ready(self, network_name: str = None):
        self.controller.wait_till_nodes_are_ready(network_name)

    def wait_till_nodes_are_ssh_ready(self):
        log.info("Wait till %s nodes will be ready for SSH connection", len(self.nodes))

        def _all_nodes_allow_ssh_connection():
            try:
                for node in self.nodes:
                    if node.ssh_connection is None:
                        return False
            except (TimeoutError, SCPException, SSHException):
                return False
            return True

        waiting.wait(
            lambda: _all_nodes_allow_ssh_connection(),
            timeout_seconds=180,
            sleep_seconds=20,
            waiting_for="nodes to allow ssh connection",
        )
        log.info("All nodes have booted, got ips, and ready for SSH")
        
    def get_controller(self):
        return self.controller
