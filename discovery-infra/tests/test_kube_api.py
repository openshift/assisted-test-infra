import base64
import errno
import json
import logging
import os
import socket
import uuid

import openshift as oc
import pytest
from junit_report import JunitTestSuite
from netaddr import IPNetwork

from test_infra import utils, consts
from test_infra.helper_classes.kube_helpers import (AgentClusterInstall,
                                                    ClusterDeployment,
                                                    ClusterImageSet,
                                                    ClusterImageSetReference,
                                                    InfraEnv, Proxy, Secret)
from test_infra.utils import download_iso, get_openshift_release_image
from test_infra.utils.kubeapi_utils import get_ip_for_single_node

from tests.base_test import BaseTest
from tests.config import EnvConfig
from download_logs import collect_debug_info_from_cluster

PROXY_PORT = 3129

logger = logging.getLogger(__name__)


class TestKubeAPISNO(BaseTest):

    @pytest.fixture
    def kube_test_configs(self, configs):
        cluster_config, tf_config = configs
        tf_config.masters_count = 1
        tf_config.workers_count = 0
        tf_config.master_vcpu = 8
        tf_config.master_memory = 35840

        yield cluster_config, tf_config

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_ipv4(self, kube_test_configs, kube_api_context, get_nodes):
        cluster_config, tf_config = kube_test_configs
        kube_api_test(kube_api_context, get_nodes(tf_config, cluster_config), cluster_config)

    @JunitTestSuite()
    @pytest.mark.kube_api
    def test_kube_api_ipv6(self, kube_test_configs, kube_api_context, proxy_server, get_nodes):
        cluster_config, tf_config = kube_test_configs
        tf_config.is_ipv6 = True
        cluster_config.service_network_cidr = consts.DEFAULT_IPV6_SERVICE_CIDR
        cluster_config.cluster_network_cidr = consts.DEFAULT_IPV6_CLUSTER_CIDR
        cluster_config.cluster_network_host_prefix = consts.DEFAULT_IPV6_HOST_PREFIX
        cluster_config.is_ipv6 = True

        kube_api_test(kube_api_context, get_nodes(tf_config, cluster_config),
                      cluster_config, proxy_server, is_ipv4=False)



def kube_api_test(kube_api_context, nodes, cluster_config, proxy_server=None, *, is_ipv4=True, is_disconnected=False):
    cluster_name = cluster_config.cluster_name

    machine_cidr = nodes.controller.get_machine_cidr()

    agent_cluster_install = AgentClusterInstall(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-agent-cluster-install',
    )

    secret = Secret(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-secret',
    )
    secret.create(pull_secret=cluster_config.pull_secret)

    cluster_deployment = ClusterDeployment(
        kube_api_client=kube_api_context.api_client,
        name=cluster_name,
    )
    cluster_deployment.create(
        agent_cluster_install_ref=agent_cluster_install.ref,
        secret=secret,
    )

    agent_cluster_install.create(
        cluster_deployment_ref=cluster_deployment.ref,
        image_set_ref=deploy_image_set(cluster_name, kube_api_context),
        cluster_cidr=cluster_config.cluster_network_cidr,
        host_prefix=cluster_config.cluster_network_host_prefix,
        service_network=cluster_config.service_network_cidr,
        ssh_pub_key=cluster_config.ssh_public_key,
        hyperthreading=cluster_config.hyperthreading,
        control_plane_agents=nodes.controller.params.master_count,
        worker_agents=nodes.controller.params.worker_count,
        machine_cidr=machine_cidr,
    )
    agent_cluster_install.wait_to_be_ready(False)

    if is_disconnected:
        logger.info('getting igntion and install config override for disconected install')
        ca_bundle = get_ca_bundle_from_hub()
        patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle)
        ignition_config_override = get_ignition_config_override(ca_bundle)
    else:
        ignition_config_override = None

    proxy = setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server)

    infra_env = InfraEnv(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-infra-env',
    )
    infra_env.create(
        cluster_deployment=cluster_deployment,
        ignition_config_override=ignition_config_override,
        secret=secret,
        proxy=proxy,
        ssh_pub_key=cluster_config.ssh_public_key,
    )
    infra_env.status()
    download_iso_from_infra_env(infra_env, cluster_config)

    logger.info('iso downloaded, starting nodes')
    nodes.start_all()

    logger.info('waiting for host agent')
    for agent in cluster_deployment.wait_for_agents(len(nodes)):
        agent.approve()
        set_agent_hostname(nodes[0], agent, is_ipv4)  # Currently only supports single node

    if len(nodes) == 1:
        set_single_node_ip(cluster_deployment, nodes, is_ipv4)

    agent_cluster_install.wait_to_be_ready(True)

    logger.info('waiting for agent-cluster-install to be in installing state')
    agent_cluster_install.wait_to_be_installing()

    try:
        logger.info('installation started, waiting for completion')
        agent_cluster_install.wait_to_be_installed()
        logger.info('installation completed successfully')
    except Exception:
        logger.exception(f"Failure during kube-api installation flow:")
        collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install)


def deploy_image_set(cluster_name, kube_api_context):
    openshift_version = os.environ.get('OPENSHIFT_VERSION', '4.8')
    openshift_release_image = get_openshift_release_image(openshift_version)

    image_set_name = f'{cluster_name}-image-set'
    image_set = ClusterImageSet(
        kube_api_client=kube_api_context.api_client,
        name=image_set_name,
    )
    image_set.create(openshift_release_image)

    return ClusterImageSetReference(image_set_name)


def setup_proxy(cluster_config, machine_cidr, cluster_name, proxy_server=None):
    if not proxy_server:
        return
    logger.info('setting cluster proxy details')
    proxy_server_name = 'squid-' + str(uuid.uuid4())[:8]
    port = utils.scan_for_free_port(PROXY_PORT)
    proxy_server(name=proxy_server_name, port=port)
    host_ip = str(IPNetwork(machine_cidr).ip + 1)
    proxy_url = f'http://[{host_ip}]:{port}'
    no_proxy = ','.join(
        [
            machine_cidr,
            cluster_config.service_network_cidr,
            cluster_config.cluster_network_cidr,
            f'.{cluster_name}.redhat.com'
        ]
    )
    return Proxy(
        http_proxy=proxy_url,
        https_proxy=proxy_url,
        no_proxy=no_proxy
    )


def download_iso_from_infra_env(infra_env, cluster_config):
    logger.info('getting iso download url')
    iso_download_url = infra_env.get_iso_download_url()
    logger.info('downloading iso from url=%s', iso_download_url)
    download_iso(iso_download_url, cluster_config.iso_download_path)
    assert os.path.isfile(cluster_config.iso_download_path)


def set_single_node_ip(cluster_deployment, nodes, is_ipv4):
    logger.info('waiting to have host single node ip')
    single_node_ip = get_ip_for_single_node(cluster_deployment, is_ipv4)
    nodes.controller.tf.change_variables({
        'single_node_ip': single_node_ip,
        'bootstrap_in_place': True,
    })
    logger.info('single node ip=%s', single_node_ip)


def set_agent_hostname(node, agent, is_ipv4):
    if is_ipv4:
        return
    logger.info('patching agent hostname=%s', node)
    agent.patch(hostname=node.name)


def get_ca_bundle_from_hub():
    os.environ['KUBECONFIG'] = EnvConfig.get("installer_kubeconfig_path")
    with oc.project(EnvConfig.get("namespace")):
        ca_config_map_objects = oc.selector('configmap/registry-ca').objects()
        assert len(ca_config_map_objects) > 0
        ca_config_map_object = ca_config_map_objects[0]
        ca_bundle = ca_config_map_object.model.data['ca-bundle.crt']
    return ca_bundle


def patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle):
    ca_bundle_json_string = json.dumps({'additionalTrustBundle': ca_bundle})
    cluster_deployment.annotate_install_config(ca_bundle_json_string)


def get_ignition_config_override(ca_bundle):
    ca_bundle_b64 = base64.b64encode(ca_bundle.encode()).decode()
    ignition_config_override = {
            "ignition": {
                "version": "3.1.0"
            },
            "storage": {
                "files": [
                    {
                        "path": "/etc/pki/ca-trust/source/anchors/domain.crt",
                        "mode": 420,
                        "overwrite": True,
                        "user": {
                            "name": "root"
                        },
                        "contents": {
                            "source": f"data:text/plain;base64,{ca_bundle_b64}"
                        }
                    }
                ]
            }
    }
    return json.dumps(ignition_config_override)
