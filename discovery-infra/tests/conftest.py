import logging
import os
import uuid
from distutils import util
from typing import List

import pytest
import test_infra.utils as infra_utils
from test_infra import assisted_service_api, consts, utils


def _get_cluster_name():
    cluster_name = utils.get_env('CLUSTER_NAME', f'{consts.CLUSTER_PREFIX}')
    if cluster_name == consts.CLUSTER_PREFIX:
        cluster_name = cluster_name + '-' + str(uuid.uuid4())[:consts.SUFFIX_LENGTH]
    return cluster_name


private_ssh_key_path_default = os.path.join(os.getcwd(), "ssh_key/key")

env_variables = {"ssh_public_key": utils.get_env('SSH_PUB_KEY'),
                 "remote_service_url": utils.get_env('REMOTE_SERVICE_URL'),
                 "pull_secret": utils.get_env('PULL_SECRET'),
                 "offline_token": utils.get_env('OFFLINE_TOKEN'),
                 "openshift_version": utils.get_openshift_version(),
                 "base_domain": utils.get_env('BASE_DOMAIN', consts.DEFAULT_BASE_DNS_DOMAIN),
                 "num_masters": int(utils.get_env('NUM_MASTERS', consts.NUMBER_OF_MASTERS)),
                 "num_workers": int(utils.get_env('NUM_WORKERS', 0)),
                 "num_day2_workers": int(utils.get_env('NUM_DAY2_WORKERS', 0)),
                 "vip_dhcp_allocation": bool(util.strtobool(utils.get_env('VIP_DHCP_ALLOCATION'))),
                 "worker_memory": int(utils.get_env('WORKER_MEMORY', '8892')),
                 "master_memory": int(utils.get_env('MASTER_MEMORY', '16984')),
                 "network_mtu": utils.get_env('NETWORK_MTU', '1500'),
                 "worker_disk": int(utils.get_env('WORKER_DISK', '21474836480')),
                 "master_disk": int(utils.get_env('MASTER_DISK', '128849018880')),
                 "storage_pool_path": utils.get_env('STORAGE_POOL_PATH', os.path.join(os.getcwd(), "storage_pool")),
                 "cluster_name": _get_cluster_name(),
                 "private_ssh_key_path": utils.get_env('PRIVATE_KEY_PATH', private_ssh_key_path_default),
                 "kubeconfig_path": utils.get_env('KUBECONFIG', ''),
                 "installer_kubeconfig_path": utils.get_env('INSTALLER_KUBECONFIG', None),
                 "log_folder": utils.get_env('LOG_FOLDER', consts.LOG_FOLDER),
                 "service_cidr": utils.get_env('SERVICE_CIDR', '172.30.0.0/16'),
                 "cluster_cidr": utils.get_env('CLUSTER_CIDR', '10.128.0.0/14'),
                 "host_prefix": int(utils.get_env('HOST_PREFIX', '23')),
                 "iso_image_type": utils.get_env('ISO_IMAGE_TYPE', consts.ImageType.FULL_ISO),
                 "worker_vcpu": utils.get_env('WORKER_CPU', consts.WORKER_CPU),
                 "master_vcpu": utils.get_env('MASTER_CPU', consts.MASTER_CPU),
                 "test_teardown": bool(util.strtobool(utils.get_env('TEST_TEARDOWN', 'true'))),
                 "namespace": utils.get_env('NAMESPACE', consts.DEFAULT_NAMESPACE),
                 "olm_operators": utils.parse_olm_operators_from_env(),
                 "platform": utils.get_env("PLATFORM", consts.Platforms.BARE_METAL),
                 "user_managed_networking": False,
                 "high_availability_mode": consts.HighAvailabilityMode.FULL,
                 "download_image": bool(util.strtobool(utils.get_env("DOWNLOAD_IMAGE", default="True"))),
                 "is_ipv6": bool(util.strtobool(utils.get_env("IPv6", default="False"))),
                 "cluster_id": utils.get_env("CLUSTER_ID"),
                 "additional_ntp_source": utils.get_env("ADDITIONAL_NTP_SOURCE", consts.DEFAULT_ADDITIONAL_NTP_SOURCE),
                 }
cluster_mid_name = infra_utils.get_random_name()

# Tests running on terraform parallel must have unique ISO file
image = utils.get_env('ISO',
                      os.path.join(consts.IMAGE_FOLDER, f'{env_variables["cluster_name"]}-{cluster_mid_name}-'
                                                        f'installer-image.iso')).strip()
env_variables["kubeconfig_path"] = f'/tmp/test_kubeconfig_{cluster_mid_name}'


env_variables["iso_download_path"] = image
env_variables["num_nodes"] = env_variables["num_workers"] + env_variables["num_masters"]


if env_variables["num_masters"] == 1:
    env_variables["high_availability_mode"] = consts.HighAvailabilityMode.NONE
    env_variables["user_managed_networking"] = True
    env_variables["vip_dhcp_allocation"] = False
    os.environ["OPENSHIFT_VERSION"] = "4.8"


if env_variables["platform"] == consts.Platforms.NONE:
    env_variables["user_managed_networking"] = True
    env_variables["vip_dhcp_allocation"] = False


@pytest.fixture(scope="session")
def api_client():
    logging.info('--- SETUP --- api_client\n')
    yield get_api_client()


def get_api_client(offline_token=env_variables['offline_token'], **kwargs):
    url = env_variables['remote_service_url']

    if not url:
        url = utils.get_local_assisted_service_url(
            env_variables['namespace'], 'assisted-service', utils.get_env('DEPLOY_TARGET'))

    return assisted_service_api.create_client(url, offline_token, **kwargs)


def get_available_openshift_versions() -> List[str]:
    available_versions = list(get_api_client().get_openshift_versions().keys())
    specific_version = utils.get_openshift_version(default=None)
    if specific_version:
        if specific_version in available_versions:
            return [specific_version]
        raise ValueError(f"Invalid version {specific_version}, can't find among versions: {available_versions}")

    return available_versions


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()

    setattr(item, "result_" + result.when, result)


# Temporary adding env variables the with same pronunciation as in InventoryClient
# Todo - Replace base_domain, num_nodes, service_cidr, service_cidr, cluster_cidr, host_prefix
env_variables["base_dns_domain"] = env_variables["base_domain"]
env_variables["nodes_count"] = env_variables["num_nodes"]
env_variables["masters_count"] = env_variables["num_masters"]
env_variables["workers_count"] = env_variables["num_workers"]
env_variables["service_network_cidr"] = env_variables["service_cidr"]
env_variables["cluster_network_cidr"] = env_variables["cluster_cidr"]
env_variables["cluster_network_host_prefix"] = env_variables["host_prefix"]
env_variables["is_static_ip"] = bool(util.strtobool(str(utils.get_env("static_ips_config", default="False"))))

# Node controller parameters
# Todo - will be moved later on refactoring env_variables
env_variables["network_name"] = env_variables.get("network_name", consts.TEST_NETWORK)
env_variables["net_asset"] = env_variables.get("net_asset")
env_variables["bootstrap_in_place"] = env_variables.get("bootstrap_in_place", False)
env_variables["single_node_ip"] = env_variables.get("single_node_ip", "")
