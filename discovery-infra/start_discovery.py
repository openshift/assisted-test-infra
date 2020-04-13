#!/usr/bin/python3

import json
import waiting
import os
import pprint
import argparse
import ipaddress
import uuid
from distutils.dir_util import copy_tree
from pathlib import Path
import utils
import consts
import bm_inventory_api


def _creat_ip_address_list(node_count, starting_ip_addr):
    return [str(ipaddress.ip_address(starting_ip_addr) + i) for i in range(node_count)]


def fill_relevant_tfvars(image_path, storage_path, nodes_count, nodes_details):
    if not os.path.exists(consts.TFVARS_JSON_FILE):
        Path(consts.TF_FOLDER).mkdir(parents=True, exist_ok=True)
        copy_tree(consts.TF_TEMPLATE, consts.TF_FOLDER)

    with open(consts.TFVARS_JSON_FILE) as _file:
        tfvars = json.load(_file)
    tfvars["image_path"] = image_path
    tfvars["master_count"] = min(nodes_count, consts.NUMBER_OF_MASTERS)
    tfvars["libvirt_master_ips"] = _creat_ip_address_list(min(nodes_count, consts.NUMBER_OF_MASTERS),
                                                          starting_ip_addr=consts.STARTING_IP_ADDRESS)
    tfvars["worker_count"] = 0 if nodes_count <= consts.NUMBER_OF_MASTERS else nodes_count - consts.NUMBER_OF_MASTERS
    tfvars["libvirt_worker_ips"] = _creat_ip_address_list(tfvars["worker_count"] or 1, starting_ip_addr=str(
            ipaddress.ip_address(consts.STARTING_IP_ADDRESS) + nodes_count))
    tfvars["libvirt_storage_pool_path"] = storage_path
    tfvars.update(nodes_details)

    with open(consts.TFVARS_JSON_FILE, "w") as _file:
        json.dump(tfvars, _file)


def create_nodes(image_path, storage_path, nodes_count, nodes_details):
    print("Creating tfvars")
    fill_relevant_tfvars(image_path, storage_path, nodes_count, nodes_details)
    print("Start running terraform")
    cmd = "make run_terraform"
    return utils.run_command(cmd)


def create_nodes_and_wait_till_registered(inventory_client, cluster, image_path, storage_path,
                                          nodes_count, nodes_details):
    create_nodes(image_path, storage_path=storage_path, nodes_count=nodes_count, nodes_details=nodes_details)
    utils.wait_till_nodes_are_ready(nodes_count=nodes_count)
    if not inventory_client:
        print("No inventory url, will not wait till nodes registration")
        return

    print("Wait till nodes will be registered")
    waiting.wait(lambda: len(inventory_client.get_cluster_hosts(cluster.id)) >= nodes_count,
                 timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
                 sleep_seconds=5, waiting_for="Nodes to be registered in inventory service")
    pprint.pprint(inventory_client.get_cluster_hosts(cluster.id))


def set_hosts_roles(client, cluster_id):
    hosts = []
    libvirt_macs = utils.get_libvirt_nodes_mac_role_ip_and_name()
    inventory_hosts = client.get_cluster_hosts(cluster_id)
    assert len(libvirt_macs) == len(inventory_hosts)
    for host in inventory_hosts:
        hw = json.loads(host["hardware_info"])
        role = [libvirt_macs[nic["mac"]]["role"] for nic in hw["nics"] if nic["mac"].lower() in libvirt_macs][0]
        hosts.append({"id": host["id"], "role": role})
    if hosts:
        client.set_hosts_roles(cluster_id=cluster_id, hosts_with_roles=hosts)


def get_ssh_key(ssh_key_path):
    if not ssh_key_path:
        return None
    with open(ssh_key_path, "r+") as ssh_file:
        return ssh_file.read().strip()


def main(pargs):
    client = None
    cluster = {}
    nodes_details = {"libvirt_worker_memory": args.worker_memory,
                     "libvirt_master_memory": args.master_memory}
    if not pargs.image:
        client = bm_inventory_api.create_client()

        cluster = client.create_cluster(consts.CLUSTER_PREFIX + str(uuid.uuid4()),
                                        ssh_public_key=get_ssh_key(pargs.ssh_key))
        nodes_details["cluster_inventory_id"] = cluster.id
        client.download_image(cluster_id=cluster.id, image_path=consts.IMAGE_PATH)

    create_nodes_and_wait_till_registered(inventory_client=client,
                                          cluster=cluster,
                                          image_path=pargs.image or consts.IMAGE_PATH,
                                          storage_path=pargs.storage_path,
                                          nodes_count=pargs.nodes_count,
                                          nodes_details=nodes_details)
    if client:
        set_hosts_roles(client, cluster.id)
        print("Printing after setting roles")
        pprint.pprint(client.get_cluster_hosts(cluster.id))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run discovery flow')
    parser.add_argument('-i', '--image', help='Run terraform with given image', type=str, default="")
    parser.add_argument('-n', '--nodes-count', help='Node count to spawn', type=int, default=4)
    parser.add_argument('-p', '--storage-path', help="Path to storage pool", type=str,
                        default=consts.STORAGE_PATH)
    parser.add_argument('-si', '--skip-inventory', help='Node count to spawn', action="store_true")
    parser.add_argument('-k', '--ssh-key', help="Path to ssh key", type=str,
                        default="")
    parser.add_argument('-mm', '--master-memory', help='Master memory (ram) in mb', type=int, default=8192)
    parser.add_argument('-wm', '--worker-memory', help='Worker memory (ram) in mb', type=int, default=8192)

    args = parser.parse_args()
    main(args)
