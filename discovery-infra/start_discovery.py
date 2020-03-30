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
import bm_inventory_api


TF_FOLDER = "build/terraform"
TFVARS_JSON_FILE = os.path.join(TF_FOLDER, "terraform.tfvars.json")
IMAGE_PATH = "/tmp/installer-image.iso"
STORAGE_PATH = "/var/lib/libvirt/openshift-images"
SSH_KEY = "ssh_key/key.pub"
NODES_REGISTERED_TIMEOUT = 120
TF_TEMPLATE = "terraform_files"
STARTING_IP_ADDRESS = "192.168.126.10"
NUMBER_OF_MASTERS = 3


def _creat_ip_address_list(node_count, starting_ip_addr):
    return [str(ipaddress.ip_address(starting_ip_addr) + i) for i in range(node_count)]


def fill_relevant_tfvars(image_path, storage_path, nodes_count=3):
    if not os.path.exists(TFVARS_JSON_FILE):
        Path(TF_FOLDER).mkdir(parents=True, exist_ok=True)
        copy_tree(TF_TEMPLATE, TF_FOLDER)

    with open(TFVARS_JSON_FILE) as _file:
        tfvars = json.load(_file)
    tfvars["image_path"] = image_path
    tfvars["master_count"] = min(nodes_count, NUMBER_OF_MASTERS)
    tfvars["libvirt_master_ips"] = _creat_ip_address_list(min(nodes_count, NUMBER_OF_MASTERS),
                                                          starting_ip_addr=STARTING_IP_ADDRESS)
    tfvars["workers_count"] = 0 if nodes_count <= NUMBER_OF_MASTERS else nodes_count - NUMBER_OF_MASTERS
    tfvars["libvirt_worker_ips"] = _creat_ip_address_list(tfvars["workers_count"] or 1, starting_ip_addr=str(
            ipaddress.ip_address(STARTING_IP_ADDRESS) + nodes_count))
    tfvars["libvirt_storage_pool_path"] = storage_path

    with open(TFVARS_JSON_FILE, "w") as _file:
        json.dump(tfvars, _file)


def create_nodes(image_path, storage_path, nodes_count=3):
    print("Creating tfvars")
    fill_relevant_tfvars(image_path, storage_path, nodes_count)
    print("Start running terraform")
    cmd = "make run_terraform"
    return utils.run_command(cmd)


def create_nodes_and_wait_till_registered(inventory_client, cluster_id, image_path, storage_path, nodes_count):
    create_nodes(image_path, storage_path=storage_path, nodes_count=nodes_count)
    wait_till_nodes_are_ready(nodes_count=nodes_count)
    if not inventory_client:
        print("No inventory url, will not wait till nodes registration")
        return

    print("Wait till nodes will be registered")
    waiting.wait(lambda: len(inventory_client.get_cluster_hosts(cluster_id)) >= nodes_count,
                 timeout_seconds=NODES_REGISTERED_TIMEOUT,
                 sleep_seconds=5, waiting_for="Nodes to be registered in inventory service")
    pprint.pprint(inventory_client.get_cluster_hosts(cluster_id))


def wait_till_nodes_are_ready(nodes_count):
    print("Wait till", nodes_count, "hosts will have ips")
    cmd = "virsh net-dhcp-leases test-infra-net | grep test-infra-cluster | wc -l"
    try:
        waiting.wait(lambda: int(utils.run_command(cmd, shell=True).strip()) >= nodes_count,
                     timeout_seconds=NODES_REGISTERED_TIMEOUT * nodes_count,
                     sleep_seconds=10, waiting_for="Nodes to have ips")
        print("All nodes have booted and got ips")
    except:
        cmd = "virsh net-dhcp-leases test-infra-net"
        print("Not all nodes are ready. Current dhcp leases are", utils.run_command(cmd, shell=True).strip())
        raise


def set_hosts_roles(client, cluster_id):
    hosts = []
    cluster_hosts = client.get_cluster_hosts(cluster_id)
    for i in range(len(cluster_hosts)):
        if i < 3:
            hosts.append({"id": cluster_hosts[i]["id"], "role": "master"})
        else:
            hosts.append({"id": cluster_hosts[i]["id"], "role": "worker"})
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
    if not pargs.image:
        i_url = utils.get_service_url("bm-inventory")
        print("Inventory url", i_url)
        client = bm_inventory_api.InventoryClient(inventory_url=i_url)
        client.wait_for_api_readiness()

        cluster = client.create_cluster("test-infra-cluster-%s" % str(uuid.uuid4()),
                                        ssh_public_key=get_ssh_key(pargs.ssh_key))
        client.download_image(cluster_id=cluster["id"], image_path=IMAGE_PATH)

    create_nodes_and_wait_till_registered(inventory_client=client,
                                          cluster_id=cluster.get("id"),
                                          image_path=pargs.image or IMAGE_PATH,
                                          storage_path=pargs.storage_path,
                                          nodes_count=pargs.nodes_count)
    if client:
        set_hosts_roles(client, cluster["id"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run discovery flow')
    parser.add_argument('-i', '--image', help='Run terraform with given image', type=str, default="")
    parser.add_argument('-n', '--nodes-count', help='Node count to spawn', type=int, default=4)
    parser.add_argument('-p', '--storage-path', help="Path to storage pool", type=str,
                        default=STORAGE_PATH)
    parser.add_argument('-si', '--skip-inventory', help='Node count to spawn', action="store_true")
    parser.add_argument('-k', '--ssh-key', help="Path to ssh key", type=str,
                        default="")
    args = parser.parse_args()
    main(args)
