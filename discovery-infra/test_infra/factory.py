from netaddr import IPNetwork

from test_infra import utils, consts
from test_infra.assisted_service_api import InventoryClient
from test_infra.controllers.nat_controller import NatController
from test_infra.controllers.node_controllers import TerraformController
from test_infra.controllers.proxy_controller.proxy_controller import ProxyController
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.nodes import Nodes
from test_infra.tools.assets import LibvirtNetworkAssets
from tests.config import TerraformConfig, ClusterConfig


def nodes_factory(config: TerraformConfig, nat: NatController):
    net_asset = LibvirtNetworkAssets()
    config.net_asset = net_asset.get()
    controller = TerraformController(config)
    nodes = Nodes(controller, config.private_ssh_key_path)

    nodes.prepare_nodes()
    nat.add_nat_rules()
    return nodes


def proxy_server_factory(cluster: Cluster, cluster_config, proxy_name: str = None):
    if not proxy_name:
        proxy_name = "squid-" + cluster_config.cluster_name.suffix

    port = utils.scan_for_free_port(consts.DEFAULT_PROXY_SERVER_PORT)
    proxy_server = ProxyController(name=proxy_name, port=port, dir=proxy_name)

    host_ip = str(IPNetwork(cluster.nodes.controller.get_machine_cidr()).ip + 1)
    proxy_url = f"http://[{host_ip}]:{consts.DEFAULT_PROXY_SERVER_PORT}"
    no_proxy = ",".join([cluster.nodes.controller.get_machine_cidr(), cluster_config.service_network_cidr,
                         cluster_config.cluster_network_cidr,
                         f".{str(cluster_config.cluster_name)}.redhat.com"])
    cluster.set_proxy_values(http_proxy=proxy_url, https_proxy=proxy_url, no_proxy=no_proxy)
    return proxy_server


def cluster_factory(nodes: Nodes, api_client: InventoryClient, cluster_config: ClusterConfig):
    cluster = Cluster(api_client=api_client, config=cluster_config, nodes=nodes)
    if cluster_config.is_ipv6:
        proxy_server_factory(cluster, cluster_config)

    return cluster
