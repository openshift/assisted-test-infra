import os
import re
import shutil
import subprocess
import waiting
from abc import ABC
import warnings
import libvirt
from typing import List, Tuple, Union

from paramiko import SSHException
from scp import SCPException

from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, utils
from assisted_test_infra.test_infra.controllers.node_controllers import ssh
from assisted_test_infra.test_infra.controllers.node_controllers.disk import Disk
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig
from assisted_test_infra.test_infra.utils.base_name import BaseName, get_name_suffix
from service_client import log
from consts import resources, consts
from tests.global_variables import DefaultVariables

class KVMs390xController(LibvirtController):
    def __init__(self, config: BaseNodesConfig, entity_config: Union[BaseClusterConfig, BaseInfraEnvConfig]):
        log.debug("KVMs390xController: --- Init --- ")
        super().__init__(config, entity_config)
        self._default_variables = DefaultVariables()
        
    @property
    def entity_name(self) -> BaseName:
        return self._entity_config.entity_name
 
    @property
    def cluster_name(self) -> str:
        warnings.warn("cluster_name is deprecated. Use Controller.entity_name instead.", DeprecationWarning)
        return self._entity_name.get()

    def destroy_all_nodes(self):
        log.info("s390x KVM: shutdown and remove all the nodes")
        self.shutdown_all_nodes()
        self.remove_all_Nodes()

    def remove_all_Nodes(self):
        log.info("s390x KVM: undfine nodes and remove all storage")
        nodes = self.list_nodes()

        for node in nodes:
            self.undefine_node(node.name) 
           
    def undefine_node(self, node_name):
        command = f"virsh -c {self.libvirt_uri} undefine {node_name} --remove-all-storage"
        output, _, _ = utils.run_command(command, shell=True) 
        log.info("Remove of Node: %s, rc=%s;", node_name, output)
    
    def prepare_nodes(self):
        self.destroy_all_nodes()
        self._create_nodes()
            
    def _create_nodes(self, running=True):
        log.debug("s390x_kvm create master nodes #:%d", self._default_variables.masters_count)
        #machine_cidr = self.get_primary_machine_cidr()
        #use_dhcp = self.use_dhcp_for_libvirt
        # if remote libvirt than the iso image need to be copied to host
        x = re.search("@", self.libvirt_uri)
        if x: 
          log.debug("Extract user and ip out of libvirt uri ... ")
          y = re.search("//", self.libvirt_uri)
          ssh_user = self.libvirt_uri[y.start() + 2: x.start()]
          x = re.search("/system", self.libvirt_uri)
          command = f"scp {self.get_download_path()} {self.libvirt_uri[y.start() + 2: x.start()]}:{self.get_download_path()}"
          output, _, _ = utils.run_command(command, shell=True) 
          
        if self.use_dhcp_for_libvirt:
            x = self._default_variables.mac_libvirt_prefix.rfind(":")
            mac_start = self._default_variables.mac_libvirt_prefix[x+1:]
            mac_prefix = self._default_variables.mac_libvirt_prefix[0:x]
            for x in range(self._config.masters_count):
                node_name: str=f"{consts.NodeRoles.MASTER}-{x}"
                command = f"virt-install --connect {self.libvirt_uri} " + \
                    f"--name {node_name} --autostart --memory " + \
                    f"{resources.DEFAULT_MASTER_MEMORY} --cpu host --vcpus={resources.DEFAULT_MASTER_CPU} " + \
                    f"--cdrom {self.get_download_path()} " + \
                    f"--disk pool={self._default_variables.disk_pool},size={self._default_variables.disk_pool_size} " + \
                    f"--network network={self._default_variables.network_name},mac={mac_prefix}:{(int(mac_start)+x):02x} " + \
                    f"--nographics " + \
                    f"--noautoconsole " \
                    f"--boot hd,cdrom " + \
                    f"--os-variant rhel9.0"
                output, _, _ = utils.run_command(command, shell=True) 
                log.info("Create Node: %s, rc=%s;", node_name, output)
                
            log.debug("s390x_kvm create worker nodes #:%d", self._default_variables.workers_count)
            for x in range(self._config.workers_count):
                node_name: str=f"{consts.NodeRoles.WORKER}-{x}"
                command = f"virt-install --connect {self.libvirt_uri} " + \
                    f"--name {node_name} --autostart --memory " + \
                    f"{resources.DEFAULT_WORKER_MEMORY} --cpu host --vcpus={resources.DEFAULT_WORKER_CPU} " + \
                    f"--cdrom {self.get_download_path()} " + \
                    f"--disk pool={self._default_variables.disk_pool},size={self._default_variables.disk_pool_size} " + \
                    f"--network network={self._default_variables.network_name},mac={mac_prefix}:{(int(mac_start)+x+self._default_variables.masters_count):02x} " + \
                    f"--nographics " + \
                    f"--noautoconsole " \
                    f"--boot hd,cdrom " + \
                    f"--os-variant rhel9.0"
                output, _, _ = utils.run_command(command, shell=True) 
                log.info("Create Node: %s, rc=%s;", node_name, output)
                
    def start_all_nodes(self):
        nodes = self.list_nodes()

        if len(nodes) == 0:
            self._create_nodes()
            return self.list_nodes()
        else:
            return super().start_all_nodes()
        
    def check_vms_for_first_reboot_and_start(self):
        log.info("Restart vms after firstboot. Current masters_count/workers_count: %d/%d", self._config.masters_count, self._config.workers_count)
        timeout=consts.CLUSTER_INSTALLATION_TIMEOUT
        interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL * 6
        # Get all domains and remove the restarted domains after start
        domains = self.libvirt_connection.listAllDomains()
        
        waiting.wait(
            lambda: self.restart_vms_after_first_reboot(domains),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"VMs to be booted first time",
        )
        
    def restart_vms_after_first_reboot(self, domains):
        nodes_found = False 
       
        for domain in domains:
            if (consts.NodeRoles.MASTER in domain.name() ) or (consts.NodeRoles.WORKER in domain.name()):
                # Only for master and worker nodes
                dom = self.libvirt_connection.lookupByName(domain.name())
                nodes_found = True
                if domain.info()[0] == libvirt.VIR_DOMAIN_SHUTOFF:
                    log.debug("Restart VM after first reboot: %s;", dom.name())
                    dom.create()
                    domains.remove(domain)
       
        return not nodes_found
    