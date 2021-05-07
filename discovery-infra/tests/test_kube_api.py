import base64
import errno
import json
import logging
import os
import socket
import uuid
from copy import deepcopy
from ipaddress import IPv4Interface, IPv6Interface

import magic
import openshift as oc
import pytest
import waiting
from netaddr import IPNetwork
from test_infra import consts
from test_infra.helper_classes.kube_helpers import (
    InstallStrategy, Proxy, deploy_default_cluster_deployment,
    deploy_default_infraenv)
from test_infra.utils import download_iso

from tests.base_test import BaseTest
from tests.conftest import env_variables

PROXY_PORT = 3129

logger = logging.getLogger(__name__)


class TestKubeAPI(BaseTest):

    @pytest.mark.kube_api
    def test_kube_api_ipv4(self, _sno_environment_variables, kube_api_context, nodes):
        sno_kube_api_test(kube_api_context, nodes)

    @pytest.mark.kube_api_local
    def test_kube_api_ipv6(self, _sno_ipv6_environment_variables, _sno_environment_variables, kube_api_context, proxy_server, nodes):
        sno_kube_api_test(kube_api_context, nodes, proxy_server, is_ipv4=False, is_disconnected=False)

    @pytest.fixture(scope='function')
    def _sno_environment_variables(self):
        orig = deepcopy(env_variables)
        env_variables['bootstrap_in_place'] = True
        env_variables['master_count'] = 1
        env_variables['num_masters'] = 1
        env_variables['num_workers'] = 0
        env_variables['num_nodes'] = 1
        yield
        env_variables.clear()
        env_variables.update(orig)

    @pytest.fixture(scope='function')
    def _sno_ipv6_environment_variables(self):
        orig = deepcopy(env_variables)
        env_variables['machine_cidr'] = '1001:db8::/120'
        env_variables['service_cidr'] = '2003:db8::/112'
        env_variables['cluster_cidr'] = '2002:db8::/53'
        env_variables['host_prefix'] = 64
        num_workers = int(env_variables.get('num_workers', 0))
        env_variables['libvirt_worker_ips'] = [[] for _ in range(num_workers)]
        env_variables['libvirt_secondary_worker_ips'] = [[] for _ in range(num_workers)]
        env_variables['ipv6'] = True
        yield
        logging.info('--- TEARDOWN --- _set_environment_variables\n')
        env_variables.clear()
        env_variables.update(orig)


def sno_kube_api_test(kube_api_context, nodes, proxy_server=None, *, is_ipv4=True, is_disconnected=False):
    cluster_name = nodes.controller.cluster_name
    deployment_file = os.environ.get('CLUSTER_DEPLOYMENT_FILE')
    infraenv_file = os.environ.get('INFRAENV_FILE')

    for crd_file in (deployment_file, infraenv_file):
        if not crd_file:
            continue
        logger.info('using crd file: %s', crd_file)

    machine_cidr = nodes.controller.get_machine_cidr()

    cluster_deployment = deploy_default_cluster_deployment(
        kube_api_client=kube_api_context.api_client,
        name=cluster_name,
        install_strategy=InstallStrategy(
            host_prefix=env_variables['host_prefix'],
            machine_cidr=machine_cidr,
            cluster_cidr=env_variables['cluster_cidr'],
            service_cidr=env_variables['service_cidr'],
            ssh_public_key=env_variables['ssh_public_key'],
            control_plane_agents=env_variables['num_masters'],
            worker_agents=env_variables['num_workers'],
        ),
        **{'filepath': deployment_file} if deployment_file else {}
    )

    if is_disconnected:
        logger.info('getting igntion and install config override for disconnected install')
        ca_bundle = get_ca_bundle_from_hub()
        patch_install_config_with_ca_bundle(cluster_deployment, ca_bundle)
        ignition_config_override = get_ignition_config_override(ca_bundle)
    else:
        ignition_config_override = None

    proxy = setup_proxy(machine_cidr, cluster_name, proxy_server)

    infraenv = deploy_default_infraenv(
        kube_api_client=kube_api_context.api_client,
        name=f'{cluster_name}-infraenv',
        cluster_deployment=cluster_deployment,
        sshAuthorizedKey=env_variables['ssh_public_key'],
        ignition_config_override=ignition_config_override,
        **{'proxy': proxy} if proxy and not infraenv_file else {},
        **{'filepath': infraenv_file} if infraenv_file else {}
    )

    download_iso_from_infraenv(infraenv)

    logger.info('iso downloaded, starting nodes')
    nodes.start_all()

    logger.info('waiting for host agent')
    agent = cluster_deployment.wait_for_agents(num_agents=1)[0]
    set_single_node_ip(agent, nodes, is_ipv4)
    agent.approve()

    assert len(nodes) == 1
    set_agent_hostname(nodes[0], agent, is_ipv4)

    logger.info("Waiting for installation to start")
    cluster_deployment.wait_to_be_installing()

    logger.info("Waiting until cluster finishes installation")
    cluster_deployment.wait_to_be_installed()

    logger.info('installation completed successfully')


def wait_for_single_node_ip(agent, is_ipv4):
    def get_bmc_address():
        status = agent.status()
        if not status:
            return
        interfaces = agent.status().get('inventory', {}).get('interfaces')
        if not interfaces:
            return
        ip_addresses = interfaces[0].get(
            'ipV4Addresses' if is_ipv4 else 'ipV6Addresses'
        )
        if not ip_addresses:
            return
        interface_class = IPv4Interface if is_ipv4 else IPv6Interface
        return str(interface_class(ip_addresses[0]).ip)

    return waiting.wait(
        get_bmc_address,
        sleep_seconds=0.5,
        timeout_seconds=500,
        waiting_for=f'single node ip of agent {agent.ref}'
    )


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


def download_iso_from_infraenv(infraenv):
    logger.info('getting iso download url')
    iso_download_url = infraenv.get_iso_download_url()
    logger.info('downloading iso from url=%s', iso_download_url)
    download_iso(iso_download_url, env_variables['iso_download_path'])
    assert os.path.isfile(env_variables['iso_download_path'])
    assert "ISO" in magic.from_file(env_variables['iso_download_path'])


def set_single_node_ip(agent, nodes, is_ipv4):
    logger.info('waiting to have host single node ip')
    single_node_ip = wait_for_single_node_ip(agent, is_ipv4)
    nodes.controller.tf.change_variables({'single_node_ip': single_node_ip})
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
