import ipaddress
import json
import os
import shutil
import warnings
from typing import Dict, List, Union

from munch import Munch
from netaddr import IPNetwork

import consts
import virsh_cleanup
from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, BaseTerraformConfig, utils
from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.tools import static_network, terraform_utils
from assisted_test_infra.test_infra.utils import TerraformControllerUtil
from assisted_test_infra.test_infra.utils.base_name import BaseName, get_name_suffix
from consts import resources
from service_client import log


class TerraformController(LibvirtController):
    def __init__(self, config: BaseTerraformConfig, entity_config: Union[BaseClusterConfig, BaseInfraEnvConfig]):
        super().__init__(config, entity_config)
        self._entity_name = self._entity_config.entity_name
        self._suffix = self._entity_name.suffix or get_name_suffix()
        self.tf_folder = config.tf_folder or self._create_tf_folder(self._entity_name.get(), config.platform)
        self.network_name = config.network_name + self._suffix
        self.params = self._terraform_params(**config.get_all())
        self.tf = terraform_utils.TerraformUtils(working_dir=self.tf_folder)
        self.master_ips = None

    @property
    def entity_name(self) -> BaseName:
        return self._entity_name

    @property
    def cluster_name(self) -> str:
        warnings.warn("cluster_name is deprecated. Use Controller.entity_name instead.", DeprecationWarning)
        return self._entity_name.get()

    def _create_tf_folder(self, name: str, platform: str):
        if isinstance(self._entity_config, BaseInfraEnvConfig):
            return TerraformControllerUtil.create_folder(name, "baremetal_infra_env")

        return TerraformControllerUtil.create_folder(name, platform)

    def _get_disk_encryption_appliance(self):
        if isinstance(self._entity_config, BaseInfraEnvConfig):
            log.debug("Infra-env is not associated with any disk-encryption configuration")
            return {}

        assert (
            self._entity_config.disk_encryption_mode in consts.DiskEncryptionMode.all()
        ), f"{self._entity_config.disk_encryption_mode} is not a supported disk encryption mode"

        master_vtpm2 = worker_vtpm2 = False

        if self._entity_config.disk_encryption_mode == consts.DiskEncryptionMode.TPM_VERSION_2:
            if self._entity_config.disk_encryption_roles == consts.DiskEncryptionRoles.ALL:
                master_vtpm2 = worker_vtpm2 = True
            elif self._entity_config.disk_encryption_roles == consts.DiskEncryptionRoles.MASTERS:
                master_vtpm2 = True
            elif self._entity_config.disk_encryption_roles == consts.DiskEncryptionRoles.WORKERS:
                worker_vtpm2 = True

        return {"master_vtpm2": master_vtpm2, "worker_vtpm2": worker_vtpm2}

    # TODO move all those to conftest and pass it as kwargs
    # TODO-2 Remove all parameters defaults after moving to new workflow and use config object instead
    def _terraform_params(self, **kwargs):
        master_boot_devices = self._config.master_boot_devices
        worker_boot_devices = self._config.worker_boot_devices
        params = {
            "libvirt_worker_memory": kwargs.get("worker_memory"),
            "libvirt_master_memory": kwargs.get("master_memory", resources.DEFAULT_MASTER_MEMORY),
            "libvirt_worker_vcpu": kwargs.get("worker_vcpu", resources.DEFAULT_MASTER_CPU),
            "libvirt_master_vcpu": kwargs.get("master_vcpu", resources.DEFAULT_MASTER_CPU),
            "worker_count": kwargs.get("workers_count", 0),
            "master_count": kwargs.get("masters_count", consts.NUMBER_OF_MASTERS),
            "machine_cidr": self.get_primary_machine_cidr(),
            "libvirt_network_name": self.network_name,
            "libvirt_network_mtu": kwargs.get("network_mtu", 1500),
            "libvirt_dns_records": kwargs.get("dns_records", {}),
            # TODO change to namespace index
            "libvirt_network_if": self._config.net_asset.libvirt_network_if,
            "libvirt_worker_disk": kwargs.get("worker_disk", resources.DEFAULT_WORKER_DISK),
            "libvirt_master_disk": kwargs.get("master_disk", resources.DEFAULT_MASTER_DISK),
            "libvirt_secondary_network_name": consts.TEST_SECONDARY_NETWORK + self._suffix,
            "libvirt_storage_pool_path": kwargs.get("storage_pool_path", os.path.join(os.getcwd(), "storage_pool")),
            # TODO change to namespace index
            "libvirt_secondary_network_if": self._config.net_asset.libvirt_secondary_network_if,
            "provisioning_cidr": self._config.net_asset.provisioning_cidr,
            "running": self._config.running,
            "single_node_ip": kwargs.get("single_node_ip", ""),
            "master_disk_count": kwargs.get("master_disk_count", resources.DEFAULT_DISK_COUNT),
            "worker_disk_count": kwargs.get("worker_disk_count", resources.DEFAULT_DISK_COUNT),
            "worker_cpu_mode": kwargs.get("worker_cpu_mode", consts.WORKER_TF_CPU_MODE),
            "master_cpu_mode": kwargs.get("master_cpu_mode", consts.MASTER_TF_CPU_MODE),
            "master_boot_devices": master_boot_devices
            if master_boot_devices is not None
            else consts.DEFAULT_BOOT_DEVICES,
            "worker_boot_devices": worker_boot_devices
            if worker_boot_devices is not None
            else consts.DEFAULT_BOOT_DEVICES,
            **self._get_disk_encryption_appliance(),
        }

        params.update(self._get_specific_tf_entity_params())
        for key in [
            "libvirt_master_ips",
            "libvirt_secondary_master_ips",
            "libvirt_worker_ips",
            "libvirt_secondary_worker_ips",
        ]:
            value = kwargs.get(key)
            if value is not None:
                params[key] = value
        return Munch.fromDict(params)

    def _get_specific_tf_entity_params(self) -> Dict[str, str]:
        if isinstance(self._entity_config, BaseClusterConfig):
            return {"cluster_name": self.entity_name.get(), "cluster_domain": self._entity_config.base_dns_domain}
        elif isinstance(self._entity_config, BaseInfraEnvConfig):
            return {"infra_env_name": self._entity_name.get()}

        return dict()

    def list_nodes(self) -> List[Node]:
        return self.list_nodes_with_name_filter(self._entity_name.get())

    # Run make run terraform -> creates vms
    def _create_nodes(self, running=True):
        log.info("Creating tfvars")

        self._fill_tfvars(running)
        log.info("Start running terraform")
        self.tf.apply()
        if self.params.running:
            self.wait_till_nodes_are_ready(network_name=self.params.libvirt_network_name)

    # Filling tfvars json files with terraform needed variables to spawn vms
    def _fill_tfvars(self, running=True):
        log.info("Filling tfvars")

        tfvars = dict()
        machine_cidr = self.get_primary_machine_cidr()

        tfvars["libvirt_uri"] = consts.LIBVIRT_URI
        tfvars["master_count"] = self.params.master_count
        log.info("Machine cidr is: %s", machine_cidr)
        master_starting_ip = str(ipaddress.ip_address(ipaddress.ip_network(machine_cidr).network_address) + 10)
        worker_starting_ip = str(
            ipaddress.ip_address(ipaddress.ip_network(machine_cidr).network_address) + 10 + tfvars["master_count"]
        )
        tfvars["image_path"] = self._entity_config.iso_download_path
        tfvars["worker_image_path"] = self._entity_config.worker_iso_download_path or tfvars["image_path"]
        self.master_ips = tfvars["libvirt_master_ips"] = self._create_address_list(
            self.params.master_count, starting_ip_addr=master_starting_ip
        )
        tfvars["libvirt_worker_ips"] = self._create_address_list(
            self.params.worker_count, starting_ip_addr=worker_starting_ip
        )
        if self._config.ingress_dns:
            for service in ["console-openshift-console", "canary-openshift-ingress", "oauth-openshift"]:
                self.params["libvirt_dns_records"][
                    ".".join([service, "apps", self._config.cluster_name, self._entity_config.base_dns_domain])
                ] = tfvars["libvirt_worker_ips"][0][0]
        tfvars["machine_cidr_addresses"] = self.get_all_machine_addresses()
        tfvars["provisioning_cidr_addresses"] = self.get_all_provisioning_addresses()
        tfvars["bootstrap_in_place"] = self._config.bootstrap_in_place

        vips = self.get_ingress_and_api_vips()
        tfvars["api_vip"] = vips["api_vip"]
        tfvars["ingress_vip"] = vips["ingress_vip"]
        tfvars["running"] = running
        tfvars["libvirt_master_macs"] = static_network.generate_macs(self.params.master_count)
        tfvars["libvirt_worker_macs"] = static_network.generate_macs(self.params.worker_count)
        tfvars["master_boot_devices"] = self.params.master_boot_devices
        tfvars["worker_boot_devices"] = self.params.worker_boot_devices
        tfvars.update(self.params)
        tfvars.update(self._secondary_tfvars())

        with open(os.path.join(self.tf_folder, consts.TFVARS_JSON_NAME), "w") as _file:
            json.dump(tfvars, _file)

    def _secondary_tfvars(self):
        provisioning_cidr = self.get_provisioning_cidr()
        secondary_master_starting_ip = str(
            ipaddress.ip_address(ipaddress.ip_network(provisioning_cidr).network_address) + 10
        )
        secondary_worker_starting_ip = str(
            ipaddress.ip_address(ipaddress.ip_network(provisioning_cidr).network_address)
            + 10
            + int(self.params.master_count)
        )
        return {
            "libvirt_secondary_worker_ips": self._create_address_list(
                self.params.worker_count, starting_ip_addr=secondary_worker_starting_ip
            ),
            "libvirt_secondary_master_ips": self._create_address_list(
                self.params.master_count, starting_ip_addr=secondary_master_starting_ip
            ),
            "libvirt_secondary_master_macs": static_network.generate_macs(self.params.master_count),
            "libvirt_secondary_worker_macs": static_network.generate_macs(self.params.worker_count),
        }

    def start_all_nodes(self):
        nodes = self.list_nodes()

        if len(nodes) == 0:
            self._create_nodes()
            return self.list_nodes()
        else:
            return super().start_all_nodes()

    def format_node_disk(self, node_name: str, disk_index: int = 0):
        log.info("Formatting disk for %s", node_name)
        self.format_disk(f"{self.params.libvirt_storage_pool_path}/{self.entity_name}/{node_name}-disk-{disk_index}")

    def get_ingress_and_api_vips(self):
        network_subnet_starting_ip = str(
            ipaddress.ip_address(ipaddress.ip_network(self.get_primary_machine_cidr()).network_address) + 100
        )
        ips = utils.create_ip_address_list(2, starting_ip_addr=str(ipaddress.ip_address(network_subnet_starting_ip)))
        return {"api_vip": ips[0], "ingress_vip": ips[1]}

    @utils.on_exception(message="Failed to run terraform delete", silent=True)
    def _create_address_list(self, num, starting_ip_addr):
        # IPv6 addresses can't be set alongside mac addresses using TF libvirt provider
        # Otherwise results: "Invalid to specify MAC address '<mac>' in network '<network>' IPv6 static host definition"
        # see https://github.com/dmacvicar/terraform-provider-libvirt/issues/396
        if self.is_ipv6:
            return utils.create_empty_nested_list(num)
        return utils.create_ip_address_nested_list(num, starting_ip_addr=starting_ip_addr)

    def get_primary_machine_cidr(self):
        # In dualstack mode the primary network is IPv4
        if self.is_ipv6 and not self.is_ipv4:
            return self._config.net_asset.machine_cidr6
        return self._config.net_asset.machine_cidr

    def get_provisioning_cidr(self):
        # In dualstack mode the primary network is IPv4
        if self.is_ipv6 and not self.is_ipv4:
            return self._config.net_asset.provisioning_cidr6
        return self._config.net_asset.provisioning_cidr

    def get_all_machine_addresses(self) -> List[str]:
        """Get all subnets that belong to the primary NIC."""
        addresses = []

        if self.is_ipv4:
            addresses.append(self._config.net_asset.machine_cidr)

        if self.is_ipv6:
            addresses.append(self._config.net_asset.machine_cidr6)

        return addresses

    def get_all_provisioning_addresses(self) -> List[str]:
        """Get all subnets that belong to the secondary NIC."""
        addresses = []

        if self.is_ipv4:
            addresses.append(self._config.net_asset.provisioning_cidr)

        if self.is_ipv6:
            addresses.append(self._config.net_asset.provisioning_cidr6)

        return addresses

    def set_dns(self, api_ip: str, ingress_ip: str) -> None:
        utils.add_dns_record(
            cluster_name=self._entity_name,
            base_dns_domain=self._entity_config.base_dns_domain,
            api_ip=api_ip,
            ingress_ip=ingress_ip,
        )

    def set_dns_for_user_managed_network(self) -> None:
        machine_cidr = self.get_primary_machine_cidr()
        nameserver_ip = str(IPNetwork(machine_cidr).ip + 1)
        self.set_dns(nameserver_ip, nameserver_ip)

    def _try_to_delete_nodes(self):
        log.info("Start running terraform delete")
        self.tf.destroy()

    def destroy_all_nodes(self, delete_tf_folder=False):
        """Runs terraform destroy and then cleans it with virsh cleanup to delete
        everything relevant.
        """

        log.info("Deleting all nodes")
        if os.path.exists(self.tf_folder):
            self._try_to_delete_nodes()

        self._delete_virsh_resources(
            self._entity_name.get(), self.params.libvirt_network_name, self.params.libvirt_secondary_network_name
        )
        tfstate_path = f"{self.tf_folder}/{consts.TFSTATE_FILE}"
        if os.path.exists(tfstate_path):
            log.info(f"Deleting tf state file: {tfstate_path}")
            os.remove(tfstate_path)

        if delete_tf_folder:
            log.info("Deleting %s", self.tf_folder)
            shutil.rmtree(self.tf_folder)

    @classmethod
    def _delete_virsh_resources(cls, *filters):
        log.info("Deleting virsh resources (filters: %s)", filters)
        skip_list = virsh_cleanup.DEFAULT_SKIP_LIST
        skip_list.extend(["minikube", "minikube-net"])
        virsh_cleanup.clean_virsh_resources(skip_list=skip_list, resource_filter=filters)

    def prepare_nodes(self):
        log.info("Preparing nodes")
        self.destroy_all_nodes()
        if not os.path.exists(self._entity_config.iso_download_path):
            utils.recreate_folder(os.path.dirname(self._entity_config.iso_download_path), force_recreate=False)
            # if file not exist lets create dummy
            utils.touch(self._entity_config.iso_download_path)
        self.params.running = False
        self._create_nodes()

    def get_cluster_network(self):
        log.info(f"Cluster network name: {self.network_name}")
        return self.network_name

    def set_single_node_ip(self, ip):
        self.tf.change_variables({"single_node_ip": ip})
