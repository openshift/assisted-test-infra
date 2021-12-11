import logging
import os

import libvirt
import waiting
import xml.dom.minidom as md

from assisted_test_infra.test_infra.logger import log
from assisted_test_infra.test_infra import utils, consts as consts
import sys
import time
import warnings


__displayed_warnings = list()
conn = libvirt.open("qemu:///system")


def warn_deprecate():
    if sys.argv[0] not in __displayed_warnings:
        if sys.argv[0].endswith("__main__.py"):
            return
        warnings.filterwarnings("default", category=PendingDeprecationWarning)

        deprecation_format = (
            f"\033[93mWARNING {sys.argv[0]} module will soon be deprecated."
            " Avoid adding new functionality to this module. For more information see "
            "https://issues.redhat.com/browse/MGMT-4975\033[0m"
        )

        warnings.warn(deprecation_format, PendingDeprecationWarning)
        __displayed_warnings.append(sys.argv[0])
        time.sleep(5)


def wait_till_nodes_are_ready(nodes_count, network_name):
    log.info("Wait till %s nodes will be ready and have ips", nodes_count)
    try:
        waiting.wait(
            lambda: len(get_network_leases(network_name)) >= nodes_count,
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT * nodes_count,
            sleep_seconds=10,
            waiting_for="Nodes to have ips",
        )
        log.info("All nodes have booted and got ips")
    except BaseException:
        log.error(
            "Not all nodes are ready. Current dhcp leases are %s",
            get_network_leases(network_name),
        )
        raise


def get_network_leases(network_name):
    warnings.warn("get_network_leases is deprecated. Use LibvirtController.get_network_leases "
                  "instead.", DeprecationWarning)
    with utils.file_lock_context():
        net = conn.networkLookupByName(network_name)
        leases = net.DHCPLeases()  # TODO: getting the information from the XML dump until dhcp-leases bug is fixed
        hosts = _get_hosts_from_network(net)
        return leases + [h for h in hosts if h["ipaddr"] not in [ls["ipaddr"] for ls in leases]]


def _get_hosts_from_network(net):
    warnings.warn("_get_hosts_from_network is deprecated. Use LibvirtController.get_network_leases "
                  "instead.", DeprecationWarning)

    desc = md.parseString(net.XMLDesc())
    try:
        hosts = (
            desc.getElementsByTagName("network")[0]
                .getElementsByTagName("ip")[0]
                .getElementsByTagName("dhcp")[0]
                .getElementsByTagName("host")
        )
        return list(
            map(
                lambda host: {
                    "mac": host.getAttribute("mac"),
                    "ipaddr": host.getAttribute("ip"),
                    "hostname": host.getAttribute("name"),
                },
                hosts,
            )
        )
    except IndexError:
        return []


def get_network_leases(network_name):
    warnings.warn("get_network_leases is deprecated. Use LibvirtController.get_network_leases "
                  "instead.", DeprecationWarning)
    with utils.file_lock_context():
        net = conn.networkLookupByName(network_name)
        leases = net.DHCPLeases()  # TODO: getting the information from the XML dump until dhcp-leases bug is fixed
        hosts = _get_hosts_from_network(net)
        return leases + [h for h in hosts if h["ipaddr"] not in [ls["ipaddr"] for ls in leases]]


# Require wait_till_nodes_are_ready has finished and all nodes are up
def get_libvirt_nodes_mac_role_ip_and_name(network_name):
    nodes_data = {}
    try:
        leases = get_network_leases(network_name)
        for lease in leases:
            nodes_data[lease["mac"]] = {
                "ip": lease["ipaddr"],
                "name": lease["hostname"],
                "role": consts.NodeRoles.WORKER
                if consts.NodeRoles.WORKER in lease["hostname"]
                else consts.NodeRoles.MASTER,
            }
        return nodes_data
    except BaseException:
        log.error(
            "Failed to get nodes macs from libvirt. Output is %s",
            get_network_leases(network_name),
        )
        raise


def get_libvirt_nodes_macs(network_name):
    return [lease["mac"] for lease in get_network_leases(network_name)]


def are_libvirt_nodes_in_cluster_hosts(client, cluster_id, num_nodes):
    try:
        hosts_macs = client.get_hosts_id_with_macs(cluster_id)
    except BaseException as e:
        log.error("Failed to get nodes macs for cluster: %s", cluster_id)
        return False
    num_macs = len([mac for mac in hosts_macs if mac != ""])
    return num_macs >= num_nodes


def extract_installer(release_image, dest):
    logging.info("Extracting installer from %s to %s", release_image, dest)
    with utils.pull_secret_file() as pull_secret:
        utils.run_command(
            f"oc adm release extract --registry-config '{pull_secret}'"
            f" --command=openshift-install --to={dest} {release_image}"
        )


def get_all_namespaced_clusters():
    if not os.path.isdir(consts.TF_FOLDER):
        return

    for dirname in os.listdir(consts.TF_FOLDER):
        res = get_name_and_namespace_from_dirname(dirname)
        if not res:
            continue
        name, namespace = res
        yield name, namespace


def get_name_and_namespace_from_dirname(dirname):
    if "__" in dirname:
        return dirname.rsplit("__", 1)

    log.warning(
        "Unable to extract cluster name and namespace from directory name %s. "
        "Directory name convention must be <cluster_name>:<namespace>",
        dirname,
    )