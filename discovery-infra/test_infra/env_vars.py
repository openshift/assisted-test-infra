import os
from pathlib import Path
from distutils import util

from test_infra import utils, consts


def is_qe_env():
    return os.environ.get('NODE_ENV') == 'QE_VM'

qe_env = is_qe_env()

private_ssh_key_path_default = os.path.join(os.getcwd(), "ssh_key/key") if not qe_env else \
    os.path.join(str(Path.home()), ".ssh/id_rsa")

env_variables = {"ssh_public_key": utils.get_env('SSH_PUB_KEY'),
                 "remote_service_url": utils.get_env('REMOTE_SERVICE_URL'),
                 "pull_secret": utils.get_env('PULL_SECRET'),
                 "offline_token": utils.get_env('OFFLINE_TOKEN'),
                 "openshift_version": utils.get_env('OPENSHIFT_VERSION', '4.6'),
                 "base_domain": utils.get_env('BASE_DOMAIN', "redhat.com"),
                 "num_masters": int(utils.get_env('NUM_MASTERS', consts.NUMBER_OF_MASTERS)),
                 "num_workers": max(2, int(utils.get_env('NUM_WORKERS', 0))),
                 "vip_dhcp_allocation": bool(util.strtobool(utils.get_env('VIP_DHCP_ALLOCATION'))),
                 "machine_cidr": utils.get_env('NETWORK_CIDR', '192.168.126.0/24'),
                 "worker_memory": int(utils.get_env('WORKER_MEMORY', '8892')),
                 "master_memory": int(utils.get_env('MASTER_MEMORY', '16984')),
                 "network_mtu": utils.get_env('NETWORK_MTU', '1500'),
                 "worker_disk": int(utils.get_env('WORKER_DISK', '21474836480')),
                 "master_disk": int(utils.get_env('MASTER_DISK', '128849018880')),
                 "storage_pool_path": utils.get_env('STORAGE_POOL_PATH', os.path.join(os.getcwd(), "storage_pool")),
                 "cluster_name": utils.get_env('CLUSTER_NAME', f'{consts.CLUSTER_PREFIX}'),
                 "private_ssh_key_path": utils.get_env('PRIVATE_KEY_PATH', private_ssh_key_path_default),
                 "kubeconfig_path": utils.get_env('KUBECONFIG', ''),
                 "log_folder": utils.get_env('LOG_FOLDER', consts.LOG_FOLDER)}

cluster_mid_name = utils.get_random_name()

# Tests running on terraform parallel must have unique ISO file
if not qe_env:
    image = utils.get_env('ISO',
                          os.path.join(consts.IMAGE_FOLDER, f'{env_variables["cluster_name"]}-{cluster_mid_name}-'
                                                            f'installer-image.iso')).strip()
    env_variables["kubeconfig_path"] = f'/tmp/test_kubeconfig_{cluster_mid_name}'
else:
    image = utils.get_env('ISO',
                          os.path.join(consts.IMAGE_FOLDER, f'{env_variables["cluster_name"]}-installer-image.iso')).\
        strip()

env_variables["iso_download_path"] = image
env_variables["num_nodes"] = env_variables["num_workers"] + env_variables["num_masters"]