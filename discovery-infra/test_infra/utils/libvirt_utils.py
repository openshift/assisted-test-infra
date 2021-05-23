import json
import logging

import libvirt
import xml.dom.minidom as md

import waiting

from logger import log
from test_infra import consts

# TODO - Temporary imports - will be removed after deleting all libvirt methods from utils.py 
import filelock
import os
from contextlib import contextmanager


# TODO - Temporary copied from utils to prevent cyclic import - 
#  will be removed after deleting all libvirt methods from utils.py
@contextmanager
def _file_lock_context(filepath='/tmp/discovery-infra.lock', timeout=300):
    logging.getLogger('filelock').setLevel(logging.ERROR)

    lock = filelock.FileLock(filepath, timeout)
    try:
        lock.acquire()
    except filelock.Timeout:
        log.info(
            'Deleting lock file: %s '
            'since it exceeded timeout of: %d seconds',
            filepath, timeout
        )
        os.unlink(filepath)
        lock.acquire()

    try:
        yield
    finally:
        lock.release()


_connection = libvirt.open("qemu:///system")


def get_libvirt_nodes_from_tf_state(network_names, tf_state):
    nodes = extract_nodes_from_tf_state(tf_state, network_names, consts.NodeRoles.MASTER)
    nodes.update(extract_nodes_from_tf_state(tf_state, network_names, consts.NodeRoles.WORKER))
    return nodes


def extract_nodes_from_tf_state(tf_state, network_names, role) -> dict:
    data = dict()
    for domains in [r["instances"] for r in tf_state.resources if
                    r["type"] == "libvirt_domain" and role in r["name"]]:
        for d in domains:
            for nic in d["attributes"]["network_interface"]:
                if nic["network_name"] not in network_names:
                    continue

                data[nic["mac"]] = {"ip": nic["addresses"], "name": d["attributes"]["name"], "role": role}

    return data


def update_hosts(client, cluster_id, libvirt_nodes, update_hostnames=False, update_roles=True):
    """
    Update names and/or roles of the hosts in a cluster from a dictionary of libvirt nodes.

    An entry from the dictionary is matched to a host by the host's MAC address (of any NIC).
    Entries that do not match any host in the cluster are ignored.

    Arguments:
        client -- An assisted service client
        cluster_id -- ID of the cluster to update
        libvirt_nodes -- A dictionary that may contain data about cluster hosts
        update_hostnames -- Whether hostnames must be set (default False)
        update_roles -- Whether host roles must be set (default True)
    """

    if not update_hostnames and not update_roles:
        logging.info("Skipping update roles and hostnames")
        return

    roles = []
    hostnames = []
    inventory_hosts = client.get_cluster_hosts(cluster_id)

    for libvirt_mac, libvirt_metadata in libvirt_nodes.items():
        for host in inventory_hosts:
            inventory = json.loads(host["inventory"])

            if libvirt_mac.lower() in map(
                    lambda interface: interface["mac_address"].lower(),
                    inventory["interfaces"],
            ):
                roles.append({"id": host["id"], "role": libvirt_metadata["role"]})
                hostnames.append({"id": host["id"], "hostname": libvirt_metadata["name"]})

    if not update_hostnames:
        hostnames = None

    if not update_roles:
        roles = None

    client.update_hosts(cluster_id=cluster_id, hosts_with_roles=roles, hosts_names=hostnames)


def get_libvirt_nodes_mac_role_ip_and_name(network_name):
    """ Require wait_till_nodes_are_ready has finished and all nodes are up """
    """ TODO - used only on start discovery """
    nodes_data = dict()
    try:
        leases = _get_network_leases(network_name)
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
        log.error("Failed to get nodes macs from libvirt. Output is %s",_get_network_leases(network_name))
        raise


def wait_till_nodes_are_ready(nodes_count, network_name):
    log.info("Wait till %s nodes will be ready and have ips", nodes_count)
    try:
        waiting.wait(
            lambda: len(_get_network_leases(network_name)) >= nodes_count,
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT * nodes_count,
            sleep_seconds=10,
            waiting_for="Nodes to have ips",
        )
        log.info("All nodes have booted and got ips")
    except BaseException:
        log.error(
            "Not all nodes are ready. Current dhcp leases are %s",
            _get_network_leases(network_name),
        )
        raise


def are_libvirt_nodes_in_cluster_hosts(client, cluster_id, num_nodes):
    hosts_macs = client.get_hosts_id_with_macs(cluster_id)
    num_macs = len([mac for mac in hosts_macs if mac != ''])
    return num_macs >= num_nodes


def get_libvirt_nodes_macs(network_name):
    return [lease["mac"] for lease in _get_network_leases(network_name)]


def _get_hosts_from_network(net):
    desc = md.parseString(net.XMLDesc())
    try:
        hosts = desc.getElementsByTagName("network")[0]. \
            getElementsByTagName("ip")[0]. \
            getElementsByTagName("dhcp")[0]. \
            getElementsByTagName("host")
        return list(map(lambda host: {"mac": host.getAttribute("mac"), "ipaddr": host.getAttribute("ip"),
                                      "hostname": host.getAttribute("name")}, hosts))
    except IndexError:
        return []


def _get_network_leases(network_name):
    with _file_lock_context():
        net = _connection.networkLookupByName(network_name)
        leases = net.DHCPLeases()  # TODO: getting the information from the XML dump until dhcp-leases bug is fixed
        hosts = _get_hosts_from_network(net)
    lips = [ls["ipaddr"] for ls in leases]
    merged = leases + [h for h in hosts if h["ipaddr"] not in lips]
    return merged
