import logging
import pytest
import os
from test_infra import consts
from test_infra import utils
from distutils import util

# TODO changes it
if os.environ.get('NODE_ENV') == 'QE_VM':
    from test_infra.controllers.node_controllers.qe_vm_controler import QeVmController as nodeController
else:
    from test_infra.controllers.node_controllers.terraform_controller import TerraformController as nodeController

env_variables = {"ssh_public_key": utils.get_env('SSH_PUB_KEY'),
                 "remote_service_url": utils.get_env('REMOTE_SERVICE_URL'),
                 "pull_secret": utils.get_env('PULL_SECRET'),
                 "OFFLINE_TOKEN": utils.get_env('OFFLINE_TOKEN'),
                 "openshift_version": utils.get_env('OPENSHIFT_VERSION', '4.6'),
                 "base_domain": utils.get_env('BASE_DOMAIN', "redhat.com"),
                 "num_masters": int(utils.get_env('NUM_MASTERS', consts.NUMBER_OF_MASTERS)),
                 "num_workers": int(utils.get_env('NUM_WORKERS', 0)),
                 "vip_dhcp_allocation": bool(util.strtobool(utils.get_env('VIP_DHCP_ALLOCATION'))),
                 "machine_cidr": utils.get_env('NETWORK_CIDR', '192.168.126.0/24'),
                 "worker_memory": int(utils.get_env('WORKER_MEMORY', '8892')),
                 "master_memory": int(utils.get_env('MASTER_MEMORY', '16984')),
                 "network_mtu": utils.get_env('NETWORK_MTU', '1500'),
                 "worker_disk": int(utils.get_env('WORKER_DISK', '21474836480')),
                 "master_disk": int(utils.get_env('WORKER_DISK', '128849018880')),
                 "storage_pool_path": utils.get_env('STORAGE_POOL_PATH', os.path.join(os.getcwd(), "storage_pool")),
                 "cluster_name": utils.get_env('CLUSTER_NAME', f'{consts.CLUSTER_PREFIX}')}

image = utils.get_env('ISO',
                      os.path.join(consts.IMAGE_FOLDER, f'{env_variables["cluster_name"]}-installer-image.iso')).strip()

env_variables["iso_download_path"] = image
env_variables["num_nodes"] = env_variables["num_workers"] + env_variables["num_masters"]


@pytest.fixture(scope="session", autouse=True)
def setup_node_controller():
    logging.info("Setup node controller")
    controller = nodeController(**env_variables)
    controller.prepare_nodes()
    yield controller
    logging.info("Teardown node controller")
    controller.destroy_all_nodes()
