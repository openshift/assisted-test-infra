

import requests
import json
import subprocess
import shlex
import wait

TFVARS_JSON_FILE = "build/terraform/terraform.tfvars.json"
IMAGE_PATH = "/tmp/installer-image.iso"
NODES_REGISTERED_TIMEOUT = 180


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


def fill_relevant_tfvars(image_path, nodes_count=3):
    with open(TFVARS_JSON_FILE) as _file:
        tfvars = json.load(_file)
    tfvars["image_path"] = image_path
    tfvars["master_count"] = nodes_count

    with open(TFVARS_JSON_FILE, "w") as _file:
        json.dump(tfvars, _file)


def run_command(command):
    process = subprocess.run(shlex.split(command), check=True, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout.strip()
    return output


def get_inventory_url():
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
    result = requests.get(inventory_url + "/api/bm-inventory/v1/nodes/")
    result.raise_for_status()
    return result.json()


def create_nodes_and_wait_till_registered(inventory_url, image_path=IMAGE_PATH, nodes_count=3):
    create_nodes(image_path, nodes_count)
    wait(lambda: len(get_registered_nodes(inventory_url)) >= nodes_count, timeout=NODES_REGISTERED_TIMEOUT,
         waiting_for="Nodes to be registered in inventory service")


if __name__ == "__main__":
    i_url = get_inventory_url()
    print("Inventory url ", i_url)
    image_data = create_image(inventory_url=i_url, name="test-infra")
    print("Image url ", image_data["download_url"])
    download_image(image_url=image_data["download_url"])
    create_nodes_and_wait_till_registered(inventory_url=i_url)
