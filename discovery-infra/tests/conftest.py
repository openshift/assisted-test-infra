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

env_variables = {"SSH_PUBLIC_KEY": utils.get_env('SSH_PUB_KEY'),
                 "REMOTE_SERVICE_URL": utils.get_env('REMOTE_SERVICE_URL'),
                 "PULL_SECRET": utils.get_env('PULL_SECRET'),
                 "OFFLINE_TOKEN": utils.get_env('OFFLINE_TOKEN'),
                 "OPENSHIFT_VERSION": utils.get_env('OPENSHIFT_VERSION', '4.6'),
                 "BASE_DOMAIN": utils.get_env('BASE_DOMAIN', "redhat.com"),
                 "NUM_MASTERS": int(utils.get_env('NUM_MASTERS', consts.NUMBER_OF_MASTERS)),
                 "NUM_WORKERS": int(utils.get_env('NUM_WORKERS', 0)),
                 "VIP_DHCP_ALLOCATION": bool(util.strtobool(utils.get_env('VIP_DHCP_ALLOCATION'))),
                 "MACHINE_CIDR": utils.get_env('NETWORK_CIDR', '192.168.126.0/24'),
                 "WORKER_MEMORY": int(utils.get_env('WORKER_MEMORY', '8892')),
                 "MASTER_MEMORY": int(utils.get_env('MASTER_MEMORY', '16984')),
                 "NETWORK_MTU": utils.get_env('NETWORK_MTU', '1500'),
                 "WORKER_DISK": int(utils.get_env('WORKER_DISK', '21474836480')),
                 "MASTER_DISK": int(utils.get_env('WORKER_DISK', '128849018880')),
                 "STORAGE_POOL_PATH": utils.get_env('STORAGE_POOL_PATH', os.path.join(os.getcwd(), "storage_pool")),
                 "CLUSTER_NAME": utils.get_env('CLUSTER_NAME', f'{consts.CLUSTER_PREFIX}')}

image = utils.get_env('ISO',
                      os.path.join(consts.IMAGE_FOLDER, f'{env_variables["CLUSTER_NAME"]}-installer-image.iso')).strip()
if consts.IMAGE_FOLDER in image:
    utils.recreate_folder(consts.IMAGE_FOLDER, force_recreate=True)

env_variables["ISO_DOWNLOAD_PATH"] = image
env_variables["NUM_NODES"] = env_variables["NUM_WORKERS"] + env_variables["NUM_MASTERS"]


@pytest.fixture(scope="session", autouse=True)
def setup_node_controller():
    logging.info("Setup node controller")
    controller = nodeController(**env_variables)
    controller.prepare_nodes()
    yield controller
    logging.info("Teardown node controller")
    controller.destroy_all_nodes()
