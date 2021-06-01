import os
import logging
import uuid
import socket
import errno
import base64
import json

import pytest
import openshift as oc

from netaddr import IPNetwork

from tests.config import TerraformConfig
from test_infra.utils import download_iso, get_openshift_release_image
from test_infra.utils.kubeapi_utils import get_ip_for_single_node
from tests.base_test import BaseTest
from tests.conftest import env_variables
from test_infra.helper_classes.kube_helpers import (
    ClusterDeployment,
    Secret,
    AgentClusterInstall,
    ClusterImageSet,
    ClusterImageSetReference,
    Proxy,
    InfraEnv,
)

PROXY_PORT = 3129

logger = logging.getLogger(__name__)


class TestKubeAPISNO(BaseTest):

    @pytest.mark.kube_api
    def test_kube_api_ipv4(self, kube_api_context, get_nodes):
        tf_config = TerraformConfig(
            masters_count=1,
            workers_count=0,
            master_vcpu=8,
            master_memory=35840
        )
        kube_api_test(kube_api_context, get_nodes(tf_config))

def kube_api_test(kube_api_context, nodes, proxy_server=None, *, is_ipv4=True, is_disconnected=False):
    cluster_name = nodes.controller.cluster_name

    machine_cidr = nodes.controller.get_machine_cidr()

    agent_cluster_install = AgentClusterInstall(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-agent-cluster-install',
    )

    secret = Secret(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-secret',
    )
    secret.create(pull_secret=env_variables['pull_secret'])

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
        cluster_cidr=env_variables['cluster_cidr'],
        host_prefix=env_variables['host_prefix'],
        service_network=env_variables['service_cidr'],
        ssh_pub_key=env_variables['ssh_public_key'],
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

    proxy = setup_proxy(machine_cidr, cluster_name, proxy_server)

    infra_env = InfraEnv(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-infra-env',
    )
    infra_env.create(
        cluster_deployment=cluster_deployment,
        ignition_config_override=ignition_config_override,
        secret=secret,
        proxy=proxy,
        ssh_pub_key=env_variables['ssh_public_key'],
    )
    infra_env.status()
    download_iso_from_infra_env(infra_env)

    logger.info('iso downloaded, starting nodes')
    nodes.start_all()

    logger.info('waiting for host agent')
    for agent in cluster_deployment.wait_for_agents(len(nodes)):
        agent.approve()
        set_agent_hostname(nodes[0], agent, is_ipv4)  # Currently supports only single-node

    if len(nodes) == 1:
        set_single_node_ip(cluster_deployment, nodes, is_ipv4)

    agent_cluster_install.wait_to_be_ready(True)

    logger.info('waiting for agent-cluster-install to be in installing state')
    agent_cluster_install.wait_to_be_installing()

    logger.info('installation started, waiting for completion')
    agent_cluster_install.wait_to_be_installed()

    logger.info('installation completed successfully')


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


def setup_proxy(machine_cidr, cluster_name, proxy_server=None):
    if not proxy_server:
        return
    logger.info('setting cluster proxy details')
    proxy_server_name = 'squid-' + str(uuid.uuid4())[:8]
    port = scan_for_free_port()
    proxy_server(name=proxy_server_name, port=port)
    host_ip = str(IPNetwork(machine_cidr).ip + 1)
    proxy_url = f'http://[{host_ip}]:{port}'
    no_proxy = ','.join(
        [
            machine_cidr,
            env_variables['service_cidr'],
            env_variables['cluster_cidr'],
            f'.{cluster_name}.redhat.com'
        ]
    )
    return Proxy(
        http_proxy=proxy_url,
        https_proxy=proxy_url,
        no_proxy=no_proxy
    )


def scan_for_free_port():
    for port in range(PROXY_PORT, PROXY_PORT + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('0.0.0.0', port))
                sock.listen()
            except OSError as e:
                if e.errno != errno.EADDRINUSE:
                    raise
                continue

            return port

    raise RuntimeError(
        'could not allocate free port for proxy'
    )


def download_iso_from_infra_env(infra_env):
    logger.info('getting iso download url')
    iso_download_url = infra_env.get_iso_download_url()
    logger.info('downloading iso from url=%s', iso_download_url)
    download_iso(iso_download_url, env_variables['iso_download_path'])
    assert os.path.isfile(env_variables['iso_download_path'])


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
    os.environ['KUBECONFIG'] = env_variables['installer_kubeconfig_path']
    with oc.project(env_variables['namespace']):
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
