import ipaddress
import json
import logging
import os
import shutil
import warnings
from typing import List

from munch import Munch
from test_infra import consts, utils, virsh_cleanup
from test_infra.consts import resources
from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from test_infra.controllers.node_controllers.node import Node
from test_infra.helper_classes.config import BaseTerraformConfig, BaseClusterConfig
from test_infra.tools import static_network, terraform_utils
from test_infra.utils.cluster_name import get_cluster_name_suffix


class TerraformController(LibvirtController):

    def __init__(self, config: BaseTerraformConfig, cluster_config: BaseClusterConfig):
        super().__init__(config.private_ssh_key_path)
        self.config = config
        self._cluster_config = cluster_config
        self.cluster_name = cluster_config.cluster_name.get()
        self._suffix = cluster_config.cluster_name.suffix or get_cluster_name_suffix()
        self.network_name = config.network_name + self._suffix
        self.tf_folder = config.tf_folder or self._create_tf_folder(self.cluster_name, config.platform)
        self.params = self._terraform_params(**config.get_all())
        self.tf = terraform_utils.TerraformUtils(working_dir=self.tf_folder)
        self.master_ips = None

    @classmethod
    def _create_tf_folder(cls, cluster_name: str, platform: str):
        tf_folder = utils.get_tf_folder(cluster_name)
        logging.info("Creating %s as terraform folder", tf_folder)
        utils.recreate_folder(tf_folder)
        utils.copy_template_tree(tf_folder, none_platform_mode=platform == consts.Platforms.NONE)
        return tf_folder

    # TODO move all those to conftest and pass it as kwargs
    # TODO-2 Remove all parameters defaults after moving to new workflow and use config object instead
    def _terraform_params(self, **kwargs):
        params = {
            "libvirt_worker_memory": kwargs.get("worker_memory"),
            "libvirt_master_memory": kwargs.get("master_memory", resources.DEFAULT_MASTER_MEMORY),
            "libvirt_worker_vcpu": kwargs.get("worker_vcpu", resources.DEFAULT_MASTER_CPU),
            "libvirt_master_vcpu": kwargs.get("master_vcpu", resources.DEFAULT_MASTER_CPU),
            "worker_count": kwargs.get("workers_count", 0),
            "master_count": kwargs.get("masters_count", consts.NUMBER_OF_MASTERS),
            "cluster_name": self.cluster_name,
            "cluster_domain": self.config.base_dns_domain,
            "machine_cidr": self.get_machine_cidr(),
            "libvirt_network_name": self.network_name,
            "libvirt_network_mtu": kwargs.get("network_mtu", 1500),
            "libvirt_dns_records": kwargs.get("dns_records", {}),
            # TODO change to namespace index
            "libvirt_network_if": self.config.net_asset.libvirt_network_if,
            "libvirt_worker_disk": kwargs.get("worker_disk", resources.DEFAULT_WORKER_DISK),
            "libvirt_master_disk": kwargs.get("master_disk", resources.DEFAULT_MASTER_DISK),
            "libvirt_secondary_network_name": consts.TEST_SECONDARY_NETWORK + self._suffix,
            "libvirt_storage_pool_path": kwargs.get("storage_pool_path", os.path.join(os.getcwd(), "storage_pool")),
            # TODO change to namespace index
            "libvirt_secondary_network_if": self.config.net_asset.libvirt_secondary_network_if,
            "provisioning_cidr": self.config.net_asset.provisioning_cidr,
            "running": True,
            "single_node_ip": kwargs.get("single_node_ip", ''),
            "master_disk_count": kwargs.get("master_disk_count", resources.DEFAULT_DISK_COUNT),
            "worker_disk_count": kwargs.get("worker_disk_count", resources.DEFAULT_DISK_COUNT),
            "worker_cpu_mode": kwargs.get("worker_cpu_mode", consts.WORKER_TF_CPU_MODE),
            "master_cpu_mode": kwargs.get("master_cpu_mode", consts.MASTER_TF_CPU_MODE)
        }
        for key in ["libvirt_master_ips", "libvirt_secondary_master_ips", "libvirt_worker_ips",
                    "libvirt_secondary_worker_ips"]:
            value = kwargs.get(key)
            if value is not None:
                params[key] = value
        return Munch.fromDict(params)

    def list_nodes(self) -> List[Node]:
        return self.list_nodes_with_name_filter(self.cluster_name)

    # Run make run terraform -> creates vms
    def _create_nodes(self, running=True):
        logging.info("Creating tfvars")

        self._fill_tfvars(running)
        logging.info('Start running terraform')
        self.tf.apply()
        if self.params.running:
            utils.wait_till_nodes_are_ready(
                nodes_count=self.params.worker_count + self.params.master_count,
                network_name=self.params.libvirt_network_name
            )

    # Filling tfvars json files with terraform needed variables to spawn vms
    def _fill_tfvars(self, running=True):
        tfvars_json_file = os.path.join(self.tf_folder, consts.TFVARS_JSON_NAME)
        logging.info("Filling tfvars")
        with open(tfvars_json_file) as _file:
            tfvars = json.load(_file)

        machine_cidr = self.get_machine_cidr()
        provisioning_cidr = self.get_provisioning_cidr()

        logging.info("Machine cidr is: %s", machine_cidr)
        master_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.ip_network(machine_cidr).network_address
            )
            + 10
        )
        worker_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.ip_network(machine_cidr).network_address
            )
            + 10
            + int(tfvars["master_count"])
        )
        tfvars['image_path'] = self._cluster_config.iso_download_path
        tfvars['master_count'] = self.params.master_count
        self.master_ips = tfvars['libvirt_master_ips'] = self._create_address_list(
            self.params.master_count, starting_ip_addr=master_starting_ip
        )
        tfvars['libvirt_worker_ips'] = self._create_address_list(
            self.params.worker_count, starting_ip_addr=worker_starting_ip
        )
        tfvars['machine_cidr_addresses'] = [machine_cidr]
        tfvars['provisioning_cidr_addresses'] = [provisioning_cidr]
        tfvars['bootstrap_in_place'] = self.config.bootstrap_in_place

        vips = self.get_ingress_and_api_vips()
        tfvars['api_vip'] = vips["api_vip"]
        tfvars['ingress_vip'] = vips["ingress_vip"]
        tfvars['running'] = running
        tfvars['libvirt_master_macs'] = static_network.generate_macs(self.params.master_count)
        tfvars['libvirt_worker_macs'] = static_network.generate_macs(self.params.worker_count)
        tfvars.update(self.params)
        tfvars.update(self._secondary_tfvars())

        with open(tfvars_json_file, "w") as _file:
            json.dump(tfvars, _file)

    def _secondary_tfvars(self):
        provisioning_cidr = self.get_provisioning_cidr()
        secondary_master_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.ip_network(provisioning_cidr).network_address
            )
            + 10
        )
        secondary_worker_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.ip_network(provisioning_cidr).network_address
            )
            + 10
            + int(self.params.master_count)
        )
        return {
            'libvirt_secondary_worker_ips': self._create_address_list(
                self.params.worker_count,
                starting_ip_addr=secondary_worker_starting_ip
            ),
            'libvirt_secondary_master_ips': self._create_address_list(
                self.params.master_count,
                starting_ip_addr=secondary_master_starting_ip
            ),
            'libvirt_secondary_master_macs': static_network.generate_macs(self.params.master_count),
            'libvirt_secondary_worker_macs': static_network.generate_macs(self.params.worker_count)
        }

    def start_all_nodes(self):
        nodes = self.list_nodes()
        if len(nodes) == 0:
            self._create_nodes()
            return self.list_nodes()
        else:
            return super().start_all_nodes()

    def format_node_disk(self, node_name: str, disk_index: int = 0):
        logging.info("Formating disk for %s", node_name)
        self.format_disk(f'{self.params.libvirt_storage_pool_path}/{self.cluster_name}/{node_name}-disk-{disk_index}')

    def get_ingress_and_api_vips(self):
        network_subnet_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.ip_network(self.get_machine_cidr()).network_address
            )
            + 100
        )
        ips = utils.create_ip_address_list(2, starting_ip_addr=str(ipaddress.ip_address(network_subnet_starting_ip)))
        return {"api_vip": ips[0], "ingress_vip": ips[1]}

    @utils.on_exception(message='Failed to run terraform delete', silent=True)
    def _create_address_list(self, num, starting_ip_addr):
        if self.config.is_ipv6:
            return utils.create_empty_nested_list(num)
        return utils.create_ip_address_nested_list(num, starting_ip_addr=starting_ip_addr)

    def get_machine_cidr(self):
        if self.config.is_ipv6:
            return self.config.net_asset.machine_cidr6
        return self.config.net_asset.machine_cidr

    def get_provisioning_cidr(self):
        if self.config.is_ipv6:
            return self.config.net_asset.provisioning_cidr6
        return self.config.net_asset.provisioning_cidr

    def _try_to_delete_nodes(self):
        logging.info('Start running terraform delete')
        self.tf.destroy()

    def destroy_all_nodes(self, delete_tf_folder=False):
        """ Runs terraform destroy and then cleans it with virsh cleanup to delete
            everything relevant.
        """

        logging.info("Deleting all nodes")
        if os.path.exists(self.tf_folder):
            self._try_to_delete_nodes()

        self._delete_virsh_resources(
            self.cluster_name,
            self.params.libvirt_network_name,
            self.params.libvirt_secondary_network_name
        )
        if delete_tf_folder:
            logging.info('Deleting %s', self.tf_folder)
            shutil.rmtree(self.tf_folder)

    @classmethod
    def _delete_virsh_resources(cls, *filters):
        logging.info('Deleting virsh resources (filters: %s)', filters)
        skip_list = virsh_cleanup.DEFAULT_SKIP_LIST
        skip_list.extend(["minikube", "minikube-net"])
        virsh_cleanup.clean_virsh_resources(
            skip_list=skip_list,
            resource_filter=filters
        )

    def prepare_nodes(self):
        logging.info("Preparing nodes")
        self.destroy_all_nodes()
        if not os.path.exists(self._cluster_config.iso_download_path):
            utils.recreate_folder(os.path.dirname(self._cluster_config.iso_download_path), force_recreate=False)
            # if file not exist lets create dummy
            utils.touch(self._cluster_config.iso_download_path)
        self.params.running = False
        self._create_nodes()

    def get_cluster_network(self):
        logging.info(f'Cluster network name: {self.network_name}')
        return self.network_name

    @property
    def network_conf(self):
        warnings.warn("network_conf will soon be deprecated. Use controller.config.net_asset instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self.config.net_asset

    @network_conf.setter
    def network_conf(self, network_conf):
        warnings.warn("network_conf will soon be deprecated. Use controller.config.net_asset instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self.config.net_asset = network_conf

    @property
    def platform(self):
        warnings.warn("platform will soon be deprecated. Use controller.config.platform instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self.config.platform

    @platform.setter
    def platform(self, platform):
        warnings.warn("platform will soon be deprecated. Use controller.config.platform instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self.config.platform = platform

    @property
    def cluster_domain(self):
        warnings.warn("cluster_domain will soon be deprecated. Use controller.config.base_dns_domain instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self.config.base_dns_domain

    @cluster_domain.setter
    def cluster_domain(self, cluster_domain):
        warnings.warn("cluster_domain will soon be deprecated. Use controller.config.base_dns_domain instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self.config.base_dns_domain = cluster_domain

    @property
    def ipv6(self):
        warnings.warn("ipv6 will soon be deprecated. Use controller.config.is_ipv6 instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self.config.is_ipv6

    @ipv6.setter
    def ipv6(self, ipv6):
        warnings.warn("ipv6 will soon be deprecated. Use controller.config.is_ipv6 instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self.config.is_ipv6 = ipv6

    @property
    def image_path(self):
        warnings.warn("image_path will soon be deprecated. Use controller.config.iso_download_path instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self._cluster_config.iso_download_path

    @image_path.setter
    def image_path(self, image_path):
        warnings.warn("image_path will soon be deprecated. Use controller.config.iso_download_path instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self._cluster_config.iso_download_path = image_path

    @property
    def bootstrap_in_place(self):
        warnings.warn("bootstrap_in_place will soon be deprecated. Use controller.config.bootstrap_in_place instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self.config.bootstrap_in_place

    @bootstrap_in_place.setter
    def bootstrap_in_place(self, bootstrap_in_place):
        warnings.warn("bootstrap_in_place will soon be deprecated. Use controller.config.bootstrap_in_place instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self.config.bootstrap_in_place = bootstrap_in_place
