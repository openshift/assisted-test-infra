import functools
import logging
from ipaddress import IPv4Interface, IPv6Interface
from pathlib import Path

import waiting
from kubernetes.client import ApiException, CoreV1Api, CustomObjectsApi

from test_infra import consts, utils
from test_infra.helper_classes.kube_helpers import ClusterDeployment, ClusterImageSet, InfraEnv, NMStateConfig, Secret

logger = logging.getLogger(__name__)


def get_ip_for_single_node(cluster_deployment, is_ipv4, timeout=300):
    agents = cluster_deployment.list_agents()
    assert len(agents) == 1
    agent = agents[0]

    def get_bmc_address():
        interfaces = agent.status().get("inventory", {}).get("interfaces")
        if not interfaces:
            return
        ip_addresses = interfaces[0].get("ipV4Addresses" if is_ipv4 else "ipV6Addresses")
        if not ip_addresses:
            return

        ip_addr = ip_addresses[0]
        ip_interface = IPv4Interface(ip_addr) if is_ipv4 else IPv6Interface(ip_addr)
        return str(ip_interface.ip)

    return waiting.wait(
        get_bmc_address,
        sleep_seconds=0.5,
        timeout_seconds=timeout,
        waiting_for=f"single node ip of agent {agent.ref}",
    )


def set_agents_hostnames(
    cluster_deployment,
    is_ipv4,
    static_network_mode,
    tf,
    nodes_number,
):
    if is_ipv4 and not static_network_mode:
        return

    logger.info("Updating agents hostnames")
    nodes_details = get_nodes_details(
        cluster_name=cluster_deployment.ref.name,
        namespace=cluster_deployment.ref.namespace,
        tf=tf,
    )
    for agent in cluster_deployment.wait_for_agents(nodes_number):
        set_agent_hostname(agent, nodes_details)


def get_nodes_details(cluster_name, namespace, tf):
    tf_folder = utils.get_tf_folder(cluster_name, namespace)
    tf_vars = utils.get_tfvars(tf_folder)
    networks_names = (
        tf_vars["libvirt_network_name"],
        tf_vars["libvirt_secondary_network_name"],
    )
    return utils.get_libvirt_nodes_from_tf_state(
        network_names=networks_names,
        tf_state=tf.get_state(),
    )


def set_agent_hostname(agent, nodes_details):
    assert len(nodes_details) >= 1
    hostname = waiting.wait(
        functools.partial(get_hostname_for_agent, agent, nodes_details),
        timeout_seconds=60,
        sleep_seconds=1,
        waiting_for=f"agent={agent.ref} to find a hostname",
    )
    logger.info("patching agent hostname=%s", hostname)
    agent.patch(hostname=hostname)


def get_hostname_for_agent(agent, nodes_details):
    inventory = agent.status().get("inventory", {})
    for mac_address, node_metadata in nodes_details.items():
        mac_address = mac_address.lower()
        for interface in inventory.get("interfaces", []):
            if interface["macAddress"].lower() == mac_address:
                return node_metadata["name"]


def suppress_not_found_error(fn):
    @functools.wraps(fn)
    def decorator(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ApiException as e:
            if e.reason == "Not Found":
                return
            raise

    return decorator


def delete_kube_api_resources_for_namespace(
    kube_api_client,
    name,
    namespace,
    *,
    secret_name=None,
    infraenv_name=None,
    nmstate_name=None,
    image_set_name=None,
):
    CoreV1Api.delete_namespaced_secret = suppress_not_found_error(
        fn=CoreV1Api.delete_namespaced_secret,
    )
    CustomObjectsApi.delete_namespaced_custom_object = suppress_not_found_error(
        fn=CustomObjectsApi.delete_namespaced_custom_object
    )

    cluster_deployment = ClusterDeployment(
        kube_api_client=kube_api_client,
        name=name,
        namespace=namespace,
    )

    for agent in cluster_deployment.list_agents():
        agent.delete()

    cluster_deployment.delete()

    Secret(
        kube_api_client=kube_api_client,
        name=secret_name or name,
        namespace=namespace,
    ).delete()

    InfraEnv(
        kube_api_client=kube_api_client,
        name=infraenv_name or f"{name}-infra-env",
        namespace=namespace,
    ).delete()

    NMStateConfig(
        kube_api_client=kube_api_client,
        name=nmstate_name or f"{name}-nmstate-config",
        namespace=namespace,
    ).delete()

    ClusterImageSet(
        kube_api_client=kube_api_client, name=image_set_name or f"{name}-image-set", namespace=namespace
    ).delete()
