import os
import re
import libvirt
import utils

import consts
from  node_controlers.node_controler import NodeControler

class QeVmController(NodeControler):

    def __init__(self):
        self.libvirt_connection = libvirt.open('qemu:///system')

    def __del__(self):
        self.libvirt_connection.close()

    def list_nodes(self):
        nodes = {}
        domains = self.libvirt_connection.listAllDomains()

        for domain in domains:
            domain_name = domain.name()
            if (consts.NodeRoles.MASTER in domain_name) or (consts.NodeRoles.WORKER in domain_name):
                domain_state = "running" if domain.isActive() else "shut_off"
                nodes[domain_name] = domain_state

        return nodes
    
    def shutdown_node(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)

        if node.isActive():
            node.destroy()

    def shutdown_all_nodes(self):
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.shutdown_node(node)

    def start_node(self, node_name):
        node = self.libvirt_connection.lookupByName(node_name)

        if node.isActive() == False:
            node.create()

    def start_all_nodes(self):
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.start_node(node)

    def restart_node(self, node_name):
        self.shutdown_node(node_name=node_name)
        self.start_node(node_name=node_name)

    def format_node_disk(self, node_name):
        command = f"qemu-img info /var/lib/libvirt/images/linchpin/{node_name}.qcow2 | grep 'virtual size'"
        output = utils.run_command(command, shell=True)        
        image_size = output[0].split(' ')[2]

        command = f'qemu-img create -f qcow2 /var/lib/libvirt/images/linchpin/{node_name}.qcow2 {image_size}'
        utils.run_command(command, shell=True)

    def format_all_node_disks(self):
        nodes = self.list_nodes()

        for node in nodes.keys():
            self.format_node_disk(node)

    def get_ingress_and_api_vips(self):

        return {"api_vip":"192.168.123.5", "ingress_vip":"192.168.123.10"}

