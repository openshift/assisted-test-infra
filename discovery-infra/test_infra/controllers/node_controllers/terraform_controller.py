import ipaddress
import os
import shutil
import json
import uuid
from munch import Munch
from distutils.dir_util import copy_tree
import logging
from test_infra import utils
from test_infra import virsh_cleanup
from test_infra import consts
from test_infra.tools import terraform_utils
from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController


class TerraformController(LibvirtController):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cluster_suffix = self._get_random_name()
        self.cluster_name = kwargs.get('cluster_name', f'{consts.CLUSTER_PREFIX}') + "-" + self.cluster_suffix
        self.network_name = kwargs.get('network_name', consts.TEST_NETWORK) + self.cluster_suffix
        self.network_conf = kwargs.get('net_asset')
        self.params = self._terraform_params(**kwargs)
        self.tf_folder = self._create_tf_folder()
        self.image_path = kwargs["iso_download_path"]
        self.tf = terraform_utils.TerraformUtils(working_dir=self.tf_folder)

    def _create_tf_folder(self):
        tf_folder = utils.get_tf_folder(self.cluster_name)
        logging.info("Creating %s as terraform folder", tf_folder)
        utils.recreate_folder(tf_folder)
        utils.copy_template_tree(tf_folder)
        return tf_folder

    def _get_random_name(self):
        return uuid.uuid4().hex[:8].lower()

    # TODO move all those to conftest and pass it as kwargs
    def _terraform_params(self, **kwargs):
        params = {"libvirt_worker_memory": kwargs.get('worker_memory'),
                  "libvirt_master_memory": kwargs.get('master_memory', 16984),
                  "worker_count": kwargs.get('num_workers', 0),
                  "master_count": kwargs.get('num_masters', consts.NUMBER_OF_MASTERS),
                  "cluster_name": self.cluster_name,
                  "cluster_domain": kwargs.get('base_domain', "redhat.com"),
                  "machine_cidr": self.network_conf.machine_cidr,
                  "libvirt_network_name": self.network_name,
                  "libvirt_network_mtu": kwargs.get('network_mtu', '1500'),
                  # TODO change to namespace index
                  "libvirt_network_if": self.network_conf.libvirt_network_if,
                  "libvirt_worker_disk": kwargs.get('worker_disk', '21474836480'),
                  "libvirt_master_disk": kwargs.get('master_disk', '128849018880'),
                  "libvirt_secondary_network_name": consts.TEST_SECONDARY_NETWORK + self.cluster_suffix,
                  "libvirt_storage_pool_path": kwargs.get('storage_pool_path',
                                                          os.path.join(os.getcwd(),
                                                                       "storage_pool")),
                  # TODO change to namespace index
                  "libvirt_secondary_network_if": self.network_conf.libvirt_secondary_network_if,
                  "provisioning_cidr": self.network_conf.provisioning_cidr,
                  "running": True
                  }
        return Munch.fromDict(params)

    def list_nodes(self):
        return self.list_nodes_with_name_filter(self.cluster_name)

    # Run make run terraform -> creates vms
    def _create_nodes(self, running=True):
        logging.info("Creating tfvars")

        self._fill_tfvars()
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
        logging.info(self.network_conf.machine_cidr)
        master_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(self.network_conf.machine_cidr).network_address
            )
            + 10
        )
        worker_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(self.network_conf.machine_cidr).network_address
            )
            + 10
            + int(tfvars["master_count"])
        )
        tfvars['image_path'] = self.image_path
        tfvars['master_count'] = self.params.master_count
        tfvars['libvirt_master_ips'] = utils.create_ip_address_nested_list(
            self.params.master_count, starting_ip_addr=master_starting_ip
        )
        tfvars['libvirt_worker_ips'] = utils.create_ip_address_nested_list(
            self.params.worker_count, starting_ip_addr=worker_starting_ip
        )
        tfvars['machine_cidr_addresses'] = [self.network_conf.machine_cidr]
        tfvars['provisioning_cidr_addresses'] = [self.network_conf.provisioning_cidr]
        tfvars['api_vip'] = self.get_ingress_and_api_vips()["api_vip"]
        tfvars['running'] = self.params.running
        tfvars.update(self.params)
        tfvars.update(self._secondary_tfvars())

        with open(tfvars_json_file, "w") as _file:
            json.dump(tfvars, _file)

    def _secondary_tfvars(self):
        secondary_master_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(self.network_conf.provisioning_cidr).network_address
            )
            + 10
        )
        secondary_worker_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(self.network_conf.provisioning_cidr).network_address
            )
            + 10
            + int(self.params.master_count)
        )
        return {
            'libvirt_secondary_worker_ips': utils.create_ip_address_nested_list(
                self.params.worker_count,
                starting_ip_addr=secondary_worker_starting_ip
            ),
            'libvirt_secondary_master_ips': utils.create_ip_address_nested_list(
                self.params.master_count,
                starting_ip_addr=secondary_master_starting_ip
            )
        }

    def start_all_nodes(self):
        nodes = self.list_nodes()
        if len(nodes) == 0:
            self._create_nodes()
            return self.list_nodes()
        else:
            return super().start_all_nodes()

    def format_node_disk(self, node_name):
        logging.info("Formating disk for %s", node_name)
        self.format_disk(f'{self.params.libvirt_storage_pool_path}/{self.cluster_name}/{node_name}')

    def get_ingress_and_api_vips(self):
        network_subnet_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(self.network_conf.machine_cidr).network_address
            )
            + 100
        )
        ips = utils.create_ip_address_list(
            2, starting_ip_addr=str(ipaddress.ip_address(network_subnet_starting_ip))
        )
        return {"api_vip": ips[0], "ingress_vip": ips[1]}

    @utils.on_exception(
        message='Failed to run terraform delete',
        silent=True
    )
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

    def _delete_virsh_resources(self, *filters):
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
        if not os.path.exists(self.image_path):
            utils.recreate_folder(os.path.dirname(self.image_path), force_recreate=False)
            # if file not exist lets create dummy
            utils.touch(self.image_path)
        self.params.running = False
        self._create_nodes()
