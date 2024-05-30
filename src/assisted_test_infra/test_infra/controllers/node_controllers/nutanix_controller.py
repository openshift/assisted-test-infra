import ipaddress
import random
import subprocess
from typing import List, Tuple, Union

from nutanix_api import NutanixApiClient, NutanixCluster, NutanixSubnet, NutanixVM
from nutanix_api.nutanix_vm import PowerState, VMBootDevices

from assisted_test_infra.test_infra.controllers.node_controllers.tf_controller import TFController
from assisted_test_infra.test_infra.helper_classes.config.base_nutanix_config import BaseNutanixConfig
from service_client import log


class NutanixController(TFController):
    _config: BaseNutanixConfig

    def _get_provider_vm(self, tf_vm_name: str) -> Union[NutanixVM, None]:
        nutanix_vms = NutanixVM.list_entities(self._provider_client)
        _, macs = self.get_node_ips_and_macs(tf_vm_name)

        for vm in nutanix_vms:
            for mac in vm.mac_addresses:
                if mac in macs:
                    return vm

        raise ValueError(f"Can't find node with name: {tf_vm_name}")

    def start_node(self, node_name: str, check_ips: bool) -> None:
        """
        :raises ValueError if node_name does not exist
        """
        vm = self._get_provider_vm(node_name)
        if vm.power_state != PowerState.ON.value:
            log.info(f"Powering on nutanix node {node_name}")
            vm.power_on()
        else:
            log.warning(
                f"Attempted to power on node {node_name}, "
                f"but the vm is already on - vm.power_state={vm.power_state}"
            )

    def shutdown_node(self, node_name: str) -> None:
        vm = self._get_provider_vm(node_name)
        if vm.power_state != PowerState.OFF.value:
            log.info(f"Powering off nutanix node {node_name}")
            vm.power_on()
        else:
            log.warning(
                f"Attempted to power off node {node_name}, "
                f"but the vm is already off - vm.power_state={vm.power_state}"
            )

    def restart_node(self, node_name: str) -> None:
        vm = self._get_provider_vm(tf_vm_name=node_name)
        vm.power_off()
        vm.power_on()

    def get_ingress_and_api_vips(self):
        """
        Need to distinguish between 3 cases:
        1) vip_dhcp_allocation is set to False: Need to provide API and Ingress VIPs - raise an exception if
        one or more are empty.
        2) vip_dhcp_allocation is set to True: No need to provide API and Ingress VIP, return None.
        3) vip_dhcp_allocation is not being set at all and its value is equal to None: In this case, search free IPs
        and set them as VIPs. The behavior is the same as vip_dhcp_allocation = False but getting the IPs first.
        Note that (3) is supposed to happen only locally due to the face that vip_dhcp_allocation is set in CI to some
        value.
        """
        if self._entity_config.vip_dhcp_allocation is False:
            if self._entity_config.api_vips is None or len(self._entity_config.api_vips) == 0:
                raise ValueError("API VIP is not set")
            if self._entity_config.ingress_vips is None or len(self._entity_config.ingress_vips) == 0:
                raise ValueError("Ingress VIP is not set")
            return {
                "api_vips": self._entity_config.api_vips,
                "ingress_vips": self._entity_config.ingress_vips,
            }

        elif self._entity_config.vip_dhcp_allocation is True:
            return None

        # If VIP DHCP Allocation is not set at all - search for free IPs and select addresses for VIPs
        nutanix_subnet = next(
            s for s in NutanixSubnet.list_entities(self._provider_client) if s.name == self._config.nutanix_subnet
        )

        free_ips = set()
        max_ping_attempts = 30
        ip_network = ipaddress.ip_network(f"{nutanix_subnet.subnet_ip}/{nutanix_subnet.prefix_length}").network_address
        attempts = 1

        log.info("Attempting to find API and Ingress VIPs...")
        while len(free_ips) < 2 and attempts < max_ping_attempts:
            attempts += 1
            address = str(ipaddress.ip_address(ip_network) + random.randint(1, 160))

            log.debug(f"Sending ping to {address} (attempt {attempts})")

            try:
                subprocess.check_output("ping -c 1 " + address, shell=True, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                free_ips.add(address)

        if len(free_ips) != 2:
            raise ConnectionError("Failed to locate free API and Ingress VIPs")

        log.info(f"Found 2 optional VIPs: {free_ips}")
        return {"api_vips": [{"ip": free_ips.pop()}], "ingress_vips": [{"ip": free_ips.pop()}]}

    def set_boot_order(self, node_name, cd_first=False, cdrom_iso_path=None) -> None:
        vm = self._get_provider_vm(tf_vm_name=node_name)
        if cd_first:
            vm.update_boot_order(VMBootDevices.default_boot_order())
        else:
            vm.update_boot_order([VMBootDevices.DISK, VMBootDevices.CDROM, VMBootDevices.NETWORK])
        if cdrom_iso_path:
            raise NotImplementedError("Updating cdrom iso file path is not implemented")

    @property
    def terraform_vm_resource_type(self) -> str:
        return "nutanix_virtual_machine"

    def _get_provider_client(self) -> NutanixApiClient:
        nutanix_client = NutanixApiClient(
            self._config.nutanix_username,
            self._config.nutanix_password,
            self._config.nutanix_port,
            self._config.nutanix_endpoint,
        )

        for c in NutanixCluster.list_entities(nutanix_client):
            if c.name == self._config.nutanix_cluster:
                break
        else:
            raise ValueError(f"Unable to locate nutanix cluster - {self._config.nutanix_cluster}")

        return nutanix_client

    def is_active(self, node_name) -> bool:
        # TODO[vrutkovs]: use Nutanix API to determine if node is running
        # Currently its assumed to be always on
        return True

    def get_cpu_cores(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["num_sockets"]

    def get_ram_kib(self, node_name: str) -> int:
        return self._get_vm(node_name)["attributes"]["memory_size_mib"] * 1024

    def get_node_ips_and_macs(self, node_name) -> Tuple[List[str], List[str]]:
        vm_attributes = self._get_vm(node_name)["attributes"]
        ips = []
        macs = []

        for nic in vm_attributes["nic_list"]:
            for ips_list in nic["ip_endpoint_list"]:
                ips.append(ips_list["ip"])

            macs.append(nic["mac_address"])

        return ips, macs
