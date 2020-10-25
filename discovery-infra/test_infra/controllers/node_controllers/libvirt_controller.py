import os
import logging
import libvirt
from test_infra import consts
from test_infra import utils
from test_infra.controllers.node_controllers.node_controller import NodeController


class LibvirtController(NodeController):

    def __init__(self, **kwargs):
        self.libvirt_connection = libvirt.open('qemu:///system')

    def __del__(self):
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
                domain_state = "running" if domain.isActive() else "shut_off"
                nodes[domain_name] = domain_state
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

    def start_all_nodes(self):
        logging.info("Going to power-on all the nodes")
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.start_node(node)

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
