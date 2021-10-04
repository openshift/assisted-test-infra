import ipaddress
import json
import logging
import os
import shutil
import warnings
from textwrap import dedent
from typing import List, Union, Dict

from munch import Munch
from netaddr import IPNetwork
from test_infra import consts, utils, virsh_cleanup
from test_infra.consts import resources
from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from test_infra.controllers.node_controllers.node import Node
from test_infra.helper_classes.config import BaseTerraformConfig, BaseClusterConfig, BaseInfraEnvConfig
from test_infra.tools import static_network, terraform_utils
from test_infra.utils.base_name import get_name_suffix, BaseName


class TerraformController(LibvirtController):

    def __init__(self, config: BaseTerraformConfig, entity_config: Union[BaseClusterConfig, BaseInfraEnvConfig]):
        super().__init__(config, entity_config)
        self._entity_name = self._get_entity_name()
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

    def _get_entity_name(self) -> BaseName:
        if isinstance(self._entity_config, BaseClusterConfig):
            return self._entity_config.cluster_name
        elif isinstance(self._entity_config, BaseInfraEnvConfig):
            return self._entity_config.entity_name
        raise Exception("Unidentified entity config")

    def _create_tf_folder(self, name: str, platform: str):
        tf_folder = utils.get_tf_folder(name)
        logging.info("Creating %s as terraform folder", tf_folder)
        utils.recreate_folder(tf_folder)
        utils.copy_template_tree(tf_folder, none_platform_mode=(platform == consts.Platforms.NONE),
                                 is_infra_env=isinstance(self._entity_config, BaseInfraEnvConfig))
        return tf_folder

    # TODO move all those to conftest and pass it as kwargs
    # TODO-2 Remove all parameters defaults after moving to new workflow and use config object instead
    def _terraform_params(self, **kwargs):
        params = {
            # Master domain
            "master_count": kwargs.get("masters_count", consts.NUMBER_OF_MASTERS),
            "master_cpu_mode": kwargs.get("master_cpu_mode", consts.MASTER_TF_CPU_MODE),
            "libvirt_master_vcpu": kwargs.get("master_vcpu", resources.DEFAULT_MASTER_CPU),
            "libvirt_master_memory": kwargs.get("master_memory", resources.DEFAULT_MASTER_MEMORY),
            "libvirt_master_disk": kwargs.get("master_disk", resources.DEFAULT_MASTER_DISK),
            "master_disk_count": kwargs.get("master_disk_count", resources.DEFAULT_DISK_COUNT),

            # Worker domain
            "worker_count": kwargs.get("workers_count", 0),
            "worker_cpu_mode": kwargs.get("worker_cpu_mode", consts.WORKER_TF_CPU_MODE),
            "libvirt_worker_vcpu": kwargs.get("worker_vcpu", resources.DEFAULT_MASTER_CPU),
            "libvirt_worker_memory": kwargs.get("worker_memory"),
            "libvirt_worker_disk": kwargs.get("worker_disk", resources.DEFAULT_WORKER_DISK),
            "worker_disk_count": kwargs.get("worker_disk_count", resources.DEFAULT_DISK_COUNT),
            
            # Networking
            "libvirt_network_name": self.network_name,
            "libvirt_network_mtu": kwargs.get("network_mtu", 1500),
            "libvirt_dns_records": kwargs.get("dns_records", {}),
            "libvirt_network_interfaces": self._config.net_asset.libvirt_network_interfaces,
            
            # Misc.
            "libvirt_storage_pool_path": kwargs.get("storage_pool_path", os.path.join(os.getcwd(), "storage_pool")),
            "running": True,
            "single_node_ip": kwargs.get("single_node_ip", ''),
        }

        params.update(self._get_specific_tf_entity_params())
        for key in ["libvirt_master_ips", "libvirt_worker_ips"]:
            value = kwargs.get(key)
            if value is not None:
                params[key] = value
        return Munch.fromDict(params)

    def _get_specific_tf_entity_params(self) -> Dict[str, str]:
        if isinstance(self._entity_config, BaseClusterConfig):
            return {
                "cluster_name": self.entity_name.get(),
                "cluster_domain": self._entity_config.base_dns_domain
            }
        elif isinstance(self._entity_config, BaseInfraEnvConfig):
            return {"infra_env_name": self._entity_name.get()}

        return dict()

    def list_nodes(self) -> List[Node]:
        return self.list_nodes_with_name_filter(self._entity_name.get())

    # Run make run terraform -> creates vms
    def _create_nodes(self, running=True):
        logging.info("Creating tfvars")

        self._fill_tfvars(running)
        logging.info('Start running terraform')
        self.tf.apply()
        if self.params.running:
            self.wait_till_nodes_are_ready(network_name=self.params.libvirt_network_name)

    # Filling tfvars json files with terraform needed variables to spawn vms
    def _fill_tfvars(self, running=True):
        tfvars_json_file = os.path.join(self.tf_folder, consts.TFVARS_JSON_NAME)
        with open(tfvars_json_file) as _file:
            tfvars = json.load(_file)

        tfvars.update(self._fill_tfvars_networking())
        tfvars['master_count'] = self.params.master_count
        tfvars['image_path'] = self._entity_config.iso_download_path
        tfvars['bootstrap_in_place'] = self._config.bootstrap_in_place
        tfvars['running'] = running

        tfvars.update(self.params)

        with open(tfvars_json_file, "w") as _file:
            json.dump(tfvars, _file)

    def _fill_tfvars_networking(self):
        tfvars = {}

        for key in ('libvirt_master_ips', 'libvirt_master_macs', 'libvirt_worker_ips', 'libvirt_worker_macs'):
            tfvars[key] = []

        tfvars['machine_cidr_addresses'] = self.get_machine_networks()
        for network in tfvars['machine_cidr_addresses']:
            master_ips, worker_ips = self._generate_ips(network)
            tfvars['libvirt_master_ips'] = self._unite_list_of_lists(tfvars['libvirt_master_ips'], master_ips)
            tfvars['libvirt_master_macs'] = self._unite_list_of_lists(tfvars['libvirt_master_macs'], 
                                                                      [[mac] for mac in static_network.generate_macs(len(master_ips))])
            tfvars['libvirt_worker_ips'] = self._unite_list_of_lists(tfvars['libvirt_worker_ips'], worker_ips)
            tfvars['libvirt_worker_macs'] = self._unite_list_of_lists(tfvars['libvirt_worker_macs'],
                                                                      [[mac] for mac in static_network.generate_macs(len(worker_ips))])

        self.master_ips = tfvars['libvirt_master_ips']

        vips = self.get_ingress_and_api_vips()
        tfvars['api_vip'] = vips["api_vip"]
        tfvars['ingress_vip'] = vips["ingress_vip"]

        return tfvars

    def _unite_list_of_lists(self, l1, l2):
        if not l1:
            return l2

        return [l1[i] + l2[i] for i in range(len(l1))]

    def _generate_ips(self, network):
        master_starting_ip = str(ipaddress.ip_address(ipaddress.ip_network(network).network_address) + 10)
        worker_starting_ip = str(ipaddress.ip_address(ipaddress.ip_network(network).network_address) + 10 + int(self.params.master_count))

        master_ips = self._create_address_list(self.params.master_count, starting_ip_addr=master_starting_ip)
        worker_ips = self._create_address_list(self.params.worker_count, starting_ip_addr=worker_starting_ip)

        return master_ips, worker_ips

    def start_all_nodes(self):
        nodes = self.list_nodes()
        if len(nodes) == 0:
            self._create_nodes()
            return self.list_nodes()
        else:
            return super().start_all_nodes()

    def format_node_disk(self, node_name: str, disk_index: int = 0):
        logging.info("Formatting disk for %s", node_name)
        self.format_disk(f'{self.params.libvirt_storage_pool_path}/{self.entity_name}/{node_name}-disk-{disk_index}')

    def get_ingress_and_api_vips(self):
        network_subnet_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.ip_network(self.get_primary_machine_cidr()).network_address
            )
            + 100
        )
        ips = utils.create_ip_address_list(2, starting_ip_addr=str(ipaddress.ip_address(network_subnet_starting_ip)))
        return {"api_vip": ips[0], "ingress_vip": ips[1]}

    @utils.on_exception(message='Failed to run terraform delete', silent=True)
    def _create_address_list(self, num, starting_ip_addr):
        # IPv6 addresses can't be set alongside mac addresses using TF libvirt provider
        # Otherwise results: "Invalid to specify MAC address '<mac>' in network '<network>' IPv6 static host definition"
        # see https://github.com/dmacvicar/terraform-provider-libvirt/issues/396
        if self.is_ipv6:
            return utils.create_empty_nested_list(num)
        return utils.create_ip_address_nested_list(num, starting_ip_addr=starting_ip_addr)

    def get_primary_machine_cidr(self) -> str:
        cidrs = self.get_machine_networks()
        assert cidrs, "There has to be at least one machine network to get a primary"

        return cidrs[0]

    def get_machine_networks(self) -> List[str]:
        cidrs = []

        # Get only the relevant cidrs from the asset according to the controller networking stack
        for cidr in self._config.net_asset.cidrs:
            ip_network = IPNetwork(cidr)

            if (ip_network.version == 4 and self.is_ipv4) or (ip_network.version == 6 and self.is_ipv6):
                cidrs.append(cidr)

        return cidrs

    def set_dns(self, api_vip: str, ingress_vip: str) -> None:
        base_domain = self._entity_config.base_dns_domain
        fname = f"/etc/NetworkManager/dnsmasq.d/openshift-{self._entity_name}.conf"
        contents = dedent(f"""
                    address=/api.{self._entity_name}.{base_domain}/{api_vip}
                    address=/.apps.{self._entity_name}.{base_domain}/{ingress_vip}
                    """)
        self.tf.change_variables(
            {"dns_forwarding_file": contents, "dns_forwarding_file_name": fname}
        )

    def set_dns_for_user_managed_network(self) -> None:
        machine_cidr = self.get_primary_machine_cidr()
        nameserver_ip = str(IPNetwork(machine_cidr).ip + 1)
        self.set_dns(nameserver_ip, nameserver_ip)

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

        # TODO: Fix delete network names
        self._delete_virsh_resources(
            self._entity_name.get(),
            self.params.libvirt_network_name,
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
        if not os.path.exists(self._entity_config.iso_download_path):
            utils.recreate_folder(os.path.dirname(self._entity_config.iso_download_path), force_recreate=False)
            # if file not exist lets create dummy
            utils.touch(self._entity_config.iso_download_path)
        self.params.running = False
        self._create_nodes()

    def get_cluster_network(self):
        logging.info(f'Cluster network name: {self.network_name}')
        return self.network_name

    def set_single_node_ip(self, ip):
        self.tf.change_variables({"single_node_ip": ip})

    @property
    def network_conf(self):
        warnings.warn("network_conf will soon be deprecated. Use controller.config.net_asset instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self._config.net_asset

    @network_conf.setter
    def network_conf(self, network_conf):
        warnings.warn("network_conf will soon be deprecated. Use controller.config.net_asset instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self._config.net_asset = network_conf

    @property
    def platform(self):
        warnings.warn("platform will soon be deprecated. Use controller.config.platform instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self._config.platform

    @platform.setter
    def platform(self, platform):
        warnings.warn("platform will soon be deprecated. Use controller.config.platform instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self._config.platform = platform

    @property
    def cluster_domain(self):
        warnings.warn("cluster_domain will soon be deprecated. Use controller.config.base_dns_domain instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self._entity_config.base_dns_domain

    @cluster_domain.setter
    def cluster_domain(self, cluster_domain):
        warnings.warn("cluster_domain will soon be deprecated. Use controller.config.base_dns_domain instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self._entity_config.base_dns_domain = cluster_domain

    @property
    def image_path(self):
        warnings.warn("image_path will soon be deprecated. Use controller.config.iso_download_path instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self._entity_config.iso_download_path

    @image_path.setter
    def image_path(self, image_path):
        warnings.warn("image_path will soon be deprecated. Use controller.config.iso_download_path instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self._entity_config.iso_download_path = image_path

    @property
    def bootstrap_in_place(self):
        warnings.warn("bootstrap_in_place will soon be deprecated. Use controller.config.bootstrap_in_place instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        return self._config.bootstrap_in_place

    @bootstrap_in_place.setter
    def bootstrap_in_place(self, bootstrap_in_place):
        warnings.warn("bootstrap_in_place will soon be deprecated. Use controller.config.bootstrap_in_place instead. "
                      "For more information see https://issues.redhat.com/browse/MGMT-4975", PendingDeprecationWarning)
        self._config.bootstrap_in_place = bootstrap_in_place
