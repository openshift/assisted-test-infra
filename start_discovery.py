#!/usr/bin/python3

import requests
import json
import subprocess
import shlex
import waiting
import os
import pprint
import argparse
import ipaddress
from retry import retry
from distutils.dir_util import copy_tree
from pathlib import Path


TF_FOLDER = "build/terraform"
TFVARS_JSON_FILE = os.path.join(TF_FOLDER, "terraform.tfvars.json")
IMAGE_PATH = "/tmp/installer-image.iso"
NODES_REGISTERED_TIMEOUT = 180
TF_TEMPLATE = "terraform_files"
STARTING_IP_ADDRESS = "192.168.126.10"


def create_image(inventory_url, name, namespace="test-infra", proxy_ip=None, proxy_port=None, description="nothing"):
    data = {"name": name,
            "namespace": namespace,
            "description": description}
    if proxy_ip and proxy_port:
        data["proxy_ip"] = proxy_ip
        data["proxy_port"] = proxy_port

    print("Creating image")
    result = requests.post(inventory_url + "/api/bm-inventory/v1/images/", json=data)
    result.raise_for_status()
    return result.json()


def download_image(image_url, image_path=IMAGE_PATH):
    print("Downloading image")
    response = requests.get(image_url, stream=True)
    handle = open(image_path, "wb")
    for chunk in response.iter_content(chunk_size=512):
        if chunk:  # filter out keep-alive new chunks
            handle.write(chunk)
    print("Finished image download")


def _creat_ip_address_list(node_count):
    return [str(ipaddress.ip_address(STARTING_IP_ADDRESS) + i) for i in range(node_count)]


def fill_relevant_tfvars(image_path, nodes_count=3):
    if not os.path.exists(TFVARS_JSON_FILE):
        Path(TF_FOLDER).mkdir(parents=True, exist_ok=True)
        copy_tree(TF_TEMPLATE, TF_FOLDER)

    with open(TFVARS_JSON_FILE) as _file:
        tfvars = json.load(_file)
    tfvars["image_path"] = image_path
    tfvars["master_count"] = nodes_count
    tfvars["libvirt_master_ips"] = _creat_ip_address_list(nodes_count)
    with open(TFVARS_JSON_FILE, "w") as _file:
        json.dump(tfvars, _file)


def run_command(command, shell=False):
    command = command if shell else shlex.split(command)
    process = subprocess.run(command, shell=shell, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout.strip()
    return output


@retry(tries=5, delay=3, backoff=2)
def get_inventory_url():
    print("Getting inventory url")
    cmd = "minikube service bm-inventory --url"
    return run_command(cmd)


def create_nodes(image_path=IMAGE_PATH, nodes_count=3):
    print("Creating tfvars")
    fill_relevant_tfvars(image_path, nodes_count)
    print("Start running terraform")
    cmd = "make run_terraform"
    return run_command(cmd)


def get_registered_nodes(inventory_url):
    print("Getting registered nodes from inventory")
    result = requests.get(inventory_url + "/api/bm-inventory/v1/hosts/", timeout=5)
    result.raise_for_status()
    return result.json()


def create_nodes_and_wait_till_registered(inventory_url, image_path=IMAGE_PATH, nodes_count=3):
    create_nodes(image_path, nodes_count)
    wait_till_nodes_are_ready(nodes_count=nodes_count)
    if not inventory_url:
        print("No inventory url, will not wait till nodes registration")
        return

    print("Wait till nodes will be registered")
    waiting.wait(lambda: len(get_registered_nodes(inventory_url)) >= nodes_count,
                 timeout_seconds=NODES_REGISTERED_TIMEOUT,
                 sleep_seconds=5, waiting_for="Nodes to be registered in inventory service")
    pprint.pprint(get_registered_nodes(inventory_url))


def wait_till_nodes_are_ready(nodes_count):
    print("Wait till ", nodes_count, " will have ips")
    cmd = "virsh net-dhcp-leases test-infra-net | grep master | wc -l"
    waiting.wait(lambda: int(run_command(cmd, shell=True).strip()) >= nodes_count,
                 timeout_seconds=NODES_REGISTERED_TIMEOUT,
                 sleep_seconds=10, waiting_for="Nodes to have ips")
    print("All nodes have booted and got ips")


def main(pargs):
    i_url = None
    if not pargs.image:
        i_url = get_inventory_url()
        print("Inventory url ", i_url)
        print("Waiting for inventory")
        waiting.wait(lambda: get_registered_nodes(i_url) is not None,
                     timeout_seconds=NODES_REGISTERED_TIMEOUT,
                     sleep_seconds=5, waiting_for="Wait till inventory is ready",
                     expected_exceptions=Exception)
        image_data = create_image(inventory_url=i_url, name="test-infra")
        print("Image url ", image_data["download_url"])
        download_image(image_url=image_data["download_url"])
    create_nodes_and_wait_till_registered(inventory_url=i_url,
                                          image_path=pargs.image or IMAGE_PATH,
                                          nodes_count=pargs.nodes_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run discovery flow')
    parser.add_argument('-i', '--image', help='Run terraform with given image', type=str, default="")
    parser.add_argument('-n', '--nodes-count', help='Node count to spawn', type=int, default=3)
    # parser.add_argument('-si', '--skip-inventory', help='Node count to spawn', type=int, default=3)
    args = parser.parse_args()
    main(args)
