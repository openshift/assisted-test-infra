import os
import time
from typing import Any, Callable, List, Tuple

from pyVim import task
from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.tf_controller import TFController
from assisted_test_infra.test_infra.utils import utils
from service_client import log


class VSphereController(TFController):
    def _get_provider_client(self) -> object:
        return None

    @property
    def terraform_vm_resource_type(self) -> str:
        return "vsphere_virtual_machine"

    def prepare_nodes(self):
        if not os.path.exists(self._entity_config.iso_download_path):
            utils.recreate_folder(os.path.dirname(self._entity_config.iso_download_path), force_recreate=False)
            # if file not exist lets create dummy
            utils.touch(self._entity_config.iso_download_path)
        config = self.get_all_vars()
        # The ISO file isn't available now until preparing for installation
        del config["iso_download_path"]

        self._create_folder(self._config.vsphere_parent_folder)
        self.tf.set_and_apply(**config)
        return self.list_nodes()

    def notify_iso_ready(self) -> None:
        self.shutdown_all_nodes()
        config = self.get_all_vars()
        self.tf.set_and_apply(**config)

    def get_cpu_cores(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["num_cpus"]

    def get_ram_kib(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["memory"] * 1024

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        vm_attributes = self._get_vm(node_name)["attributes"]

        ips = vm_attributes["guest_ip_addresses"]
        macs = []

        for interface in vm_attributes["network_interface"]:
            macs.append(interface["mac_address"])

        return ips, macs

    def destroy_all_nodes(self) -> None:
        self.tf.destroy(force=False)

    def start_node(self, node_name: str, check_ips: bool) -> None:
        def start(vm) -> task:
            return vm.PowerOn()

        self.__run_on_vm(node_name, start)

    def start_all_nodes(self) -> List[Node]:
        nodes = self.list_nodes()

        for node in nodes:
            self.start_node(node.name, False)

        return self.list_nodes()

    def shutdown_node(self, node_name: str) -> None:
        log.info(f"Powering off vm {node_name}")

        def shutdown(vm) -> task:
            return vm.PowerOff()

        self.__run_on_vm(node_name, shutdown)

    def shutdown_all_nodes(self) -> None:
        nodes = self.list_nodes()

        for node in nodes:
            self.shutdown_node(node.name)

    def restart_node(self, node_name: str) -> None:
        def reboot(vm) -> task:
            return vm.ResetVM_Task()

        self.__run_on_vm(node_name, reboot)

    def is_active(self, node_name) -> bool:
        # TODO[vrutkovs]: use vSphere API to determine if node is running
        # Currently its assumed to be always on
        return True

    def _create_folder(self, name: str):
        connection = self.__new_connection()
        content = connection.RetrieveContent()
        datacenter = VSphereController.__search_for_obj(content, vim.Datacenter, self._config.vsphere_datacenter)

        if datacenter is None:
            raise ValueError(f"""Unable to locate Datacenter ${self._config.vsphere_datacenter}""")

        folder = VSphereController.__search_for_obj(content, vim.Folder, name)

        if folder:
            log.info(f"Folder {name} already exists")
            return

        log.info(f"Creating folder {name}")
        datacenter.vmFolder.CreateFolder(name)

    def __run_on_vm(self, name: str, action: Callable) -> None:
        connection = self.__new_connection()
        content = connection.RetrieveContent()
        vm = VSphereController.__search_for_obj(content, vim.VirtualMachine, name)

        if vm is None:
            raise ValueError(f"""Unable to locate VirtualMachine ${name}""")

        vm_task = action(vm)

        while vm_task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            time.sleep(1)

        Disconnect(connection)

    def __new_connection(self):
        return SmartConnect(
            host=self._config.vsphere_server,
            user=self._config.vsphere_username,
            pwd=self._config.vsphere_password,
            disableSslCertValidation=True,
        )

    @staticmethod
    def __search_for_obj(content, vim_type, name) -> Any:
        obj = None
        container = content.viewManager.CreateContainerView(content.rootFolder, [vim_type], True)

        for managed_object_ref in container.view:
            if managed_object_ref.name == name:
                obj = managed_object_ref
                break

        container.Destroy()
        return obj
