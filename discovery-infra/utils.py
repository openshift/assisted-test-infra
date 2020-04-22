import os
import subprocess
import shlex
import waiting
import json
import pprint
from retry import retry
import consts

VIRSH_LEASES_COMMAND = "virsh -q net-dhcp-leases"


def run_command(command, shell=False):
    command = command if shell else shlex.split(command)
    process = subprocess.run(command, shell=shell, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout.strip()
    return output


def run_command_with_output(command):
    with subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            print(line, end='')  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


@retry(tries=5, delay=3, backoff=2)
def get_service_url_with_retries(service_name):
    return get_service_url(service_name)


def get_service_url(service_name):
    try:
        print("Getting inventory url")
        cmd = "minikube service %s --url" % service_name
        return run_command(cmd)
    except:
        print("Failed to get inventory url")
        raise


def wait_till_nodes_are_ready(nodes_count, cluster_name):
    print("Wait till", nodes_count, "hosts will have ips")
    cmd = "%s %s| grep %s | wc -l" % (VIRSH_LEASES_COMMAND, consts.TEST_NETWORK, cluster_name)
    try:
        waiting.wait(lambda: int(run_command(cmd, shell=True).strip()) >= nodes_count,
                     timeout_seconds=consts.NODES_REGISTERED_TIMEOUT * nodes_count,
                     sleep_seconds=10, waiting_for="Nodes to have ips")
        print("All nodes have booted and got ips")
    except:
        cmd = "%s %s" % (VIRSH_LEASES_COMMAND, consts.TEST_NETWORK)
        print("Not all nodes are ready. Current dhcp leases are", run_command(cmd, shell=False).strip())
        raise


# Require wait_till_nodes_are_ready has finished and all nodes are up
def get_libvirt_nodes_mac_role_ip_and_name():
    print("Get nodes macs and roles from libvirt")
    cmd = "%s %s" % (VIRSH_LEASES_COMMAND, consts.TEST_NETWORK)
    nodes_data = {}
    try:
        output = run_command(cmd, shell=False).splitlines()
        for node in output:
            nic_data = node.split()
            nodes_data[nic_data[2].lower()] = {"ip": nic_data[4].split("/")[0],
                                               "name": nic_data[5],
                                               "role": consts.NodeRoles.WORKER if
                                               consts.NodeRoles.WORKER in nic_data[5] else consts.NodeRoles.MASTER}
        return nodes_data
    except:
        cmd = "%s %s" % (VIRSH_LEASES_COMMAND, consts.TEST_NETWORK)
        print("Failed to get nodes macs from libvirt. Output is ", run_command(cmd, shell=False))
        raise


def get_tfvars():
    if not os.path.exists(consts.TFVARS_JSON_FILE):
        raise Exception("%s doesn't exists" % consts.TFVARS_JSON_FILE)
    with open(consts.TFVARS_JSON_FILE) as _file:
        tfvars = json.load(_file)
    return tfvars


def wait_till_all_hosts_are_in_status(client, cluster_id, nodes_count, status):
    print("Wait till", nodes_count, "nodes are in status", status)
    try:
        waiting.wait(lambda: len(client.get_hosts_in_status(cluster_id, status)) >= nodes_count,
                     timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
                     sleep_seconds=5, waiting_for="Nodes to be in status %s" % status)
    except:
        print("All nodes:")
        pprint.pprint(client.get_cluster_hosts(cluster_id))
        raise
