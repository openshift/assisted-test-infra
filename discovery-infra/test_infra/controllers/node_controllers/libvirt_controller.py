import os
import logging
import libvirt
import waiting
from contextlib import suppress
from test_infra import utils
from test_infra import consts
from test_infra.controllers.node_controllers.host import Host
from test_infra.controllers.node_controllers.node_controller import NodeController


class LibvirtController(NodeController):

    def __init__(self, **kwargs):
        self.libvirt_connection = libvirt.open('qemu:///system')
        self.private_ssh_key_path = kwargs.get("private_ssh_key_path")

    def __del__(self):
        with suppress(Exception):
            self.libvirt_connection.close()

    def list_nodes(self):
        return self.list_nodes_with_name_filter(None)

    def list_nodes_with_name_filter(self, name_filter):
        logging.info("Listing current hosts with name filter %s", name_filter)
        nodes = {}
        domains = self.libvirt_connection.listAllDomains()
        for domain in domains:
            domain_name = domain.name()
            if name_filter and name_filter not in domain_name:
                continue
            if (consts.NodeRoles.MASTER in domain_name) or (consts.NodeRoles.WORKER in domain_name):
                nodes[domain_name] = Host(domain_name, self, self.private_ssh_key_path)
        logging.info("Found domains %s", nodes)
        return nodes

    def shutdown_node(self, node_name):
        logging.info("Going to shutdown %s", node_name)
        node = self.libvirt_connection.lookupByName(node_name)

        if node.isActive():
            node.destroy()

    def shutdown_all_nodes(self):
        logging.info("Going to shutdown all the nodes")
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.shutdown_node(node)

    def start_node(self, node_name):
        logging.info("Going to power-on %s", node_name)
        node = self.libvirt_connection.lookupByName(node_name)

        if not node.isActive():
            node.create()
            self._wait_till_domain_has_ips(node)

    def start_all_nodes(self):
        logging.info("Going to power-on all the nodes")
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.start_node(node)
        return nodes

    @staticmethod
    def format_disk(disk_path):
        logging.info("Formatting disk %s", disk_path)
        if not os.path.exists(disk_path):
            logging.info("Path to %s disk not exists. Skipping")
            return

        command = f"qemu-img info {disk_path} | grep 'virtual size'"
        output = utils.run_command(command, shell=True)
        image_size = output[0].split(' ')[2]

        command = f'qemu-img create -f qcow2 {disk_path} {image_size}'
        utils.run_command(command, shell=True)

    def restart_node(self, node_name):
        logging.info("Restarting %s", node_name)
        self.shutdown_node(node_name=node_name)
        self.start_node(node_name=node_name)

    def format_all_node_disks(self):
        logging.info("Formatting all the disks")
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.format_node_disk(node)

    def prepare_nodes(self):
        self.destroy_all_nodes()

    def destroy_all_nodes(self):
        logging.info("Delete all the nodes")
        self.shutdown_all_nodes()
        self.format_all_node_disks()

    def is_active(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)
        return node.isActive()

    def get_node_ips_and_macs(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)
        return self._get_domain_ips_and_macs(node)

    def _get_domain_ips_and_macs(self, domain):
        interfaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)
        ips = []
        macs = []
        if interfaces:
            for (_, val) in interfaces.items():
                if val['addrs']:
                    for addr in val['addrs']:
                        ips.append(addr['addr'])
                        macs.append(val['hwaddr'])
        if ips:
            logging.info("Host %s ips are %s", domain.name(), ips)
        if macs:
            logging.info("Host %s macs are %s", domain.name(), macs)
        return ips, macs

    def _get_domain_ips(self, domain):
        ips, _ = self._get_domain_ips_and_macs(domain)
        return ips

    def _wait_till_domain_has_ips(self, domain, timeout=120, interval=5):
        logging.info("Waiting till host %s will have ips", domain.name())
        waiting.wait(
            lambda: len(self._get_domain_ips(domain)) > 0,
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Waiting for Ips",
        )
