#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import dns.resolver
import ipaddress
import json
import os
import time
import uuid
from functools import partial
from distutils.dir_util import copy_tree
import distutils.util
from pathlib import Path
from netaddr import IPNetwork

import assisted_service_api
import consts
import install_cluster
import utils
import oc_utils
import day2
import waiting
from logger import log
from test_infra.tools import terraform_utils


# Filling tfvars json files with terraform needed variables to spawn vms
def fill_tfvars(
        image_path,
        storage_path,
        master_count,
        nodes_details,
        tf_folder
        ):
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    master_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(nodes_details["machine_cidr"]).network_address
        )
        + 10
    )
    worker_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(nodes_details["machine_cidr"]).network_address
        )
        + 10
        + int(tfvars["master_count"])
    )
    master_count = min(master_count, consts.NUMBER_OF_MASTERS)
    tfvars['image_path'] = image_path
    tfvars['master_count'] = master_count
    tfvars['libvirt_master_ips'] = utils.create_ip_address_list(
        master_count, starting_ip_addr=master_starting_ip
    )
    tfvars['libvirt_worker_ips'] = utils.create_ip_address_list(
        nodes_details['worker_count'], starting_ip_addr=worker_starting_ip
    )
    tfvars['api_vip'] = _get_vips_ips()[0]
    tfvars['libvirt_storage_pool_path'] = storage_path
    tfvars.update(nodes_details)

    tfvars.update(_secondary_tfvars(master_count, nodes_details))

    with open(tfvars_json_file, "w") as _file:
        json.dump(tfvars, _file)


def _secondary_tfvars(master_count, nodes_details):
    secondary_master_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(nodes_details['provisioning_cidr']).network_address
        )
        + 10
    )
    secondary_worker_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(nodes_details['provisioning_cidr']).network_address
        )
        + 10
        + int(master_count)
    )
    return {
        'libvirt_secondary_worker_ips': utils.create_ip_address_list(
            nodes_details['worker_count'],
            starting_ip_addr=secondary_worker_starting_ip
        ),
        'libvirt_secondary_master_ips': utils.create_ip_address_list(
            master_count,
            starting_ip_addr=secondary_master_starting_ip
        )
    }


# Run make run terraform -> creates vms
def create_nodes(
        cluster_name,
        image_path,
        storage_path,
        master_count,
        nodes_details,
        tf
        ):
    log.info("Creating tfvars")
    fill_tfvars(
        image_path=image_path,
        storage_path=storage_path,
        master_count=master_count,
        nodes_details=nodes_details,
        tf_folder=tf.working_dir
    )
    log.info('Start running terraform')
    with utils.file_lock_context():
        return tf.apply()


# Starts terraform nodes creation, waits till all nodes will get ip and will move to known status
def create_nodes_and_wait_till_registered(
        cluster_name,
        inventory_client,
        cluster,
        image_path,
        storage_path,
        master_count,
        nodes_details,
        tf
        ):
    nodes_count = master_count + nodes_details["worker_count"]
    create_nodes(
        cluster_name=cluster_name,
        image_path=image_path,
        storage_path=storage_path,
        master_count=master_count,
        nodes_details=nodes_details,
        tf=tf
    )

    # TODO: Check for only new nodes
    utils.wait_till_nodes_are_ready(
        nodes_count=nodes_count, network_name=nodes_details["libvirt_network_name"]
    )
    if not inventory_client:
        log.info("No inventory url, will not wait till nodes registration")
        return

    log.info("Wait till nodes will be registered")
    waiting.wait(
        lambda: utils.are_all_libvirt_nodes_in_cluster_hosts(
            inventory_client, cluster.id, nodes_details["libvirt_network_name"]
        ),
        timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
        sleep_seconds=10,
        waiting_for="Nodes to be registered in inventory service",
    )


# Set nodes roles by vm name
# If master in name -> role will be master, same for worker
def set_hosts_roles(client, cluster_id, network_name):
    added_hosts = []
    libvirt_nodes = utils.get_libvirt_nodes_mac_role_ip_and_name(network_name)
    inventory_hosts = client.get_cluster_hosts(cluster_id)

    for libvirt_mac, libvirt_metadata in libvirt_nodes.items():
        for host in inventory_hosts:
            inventory = json.loads(host["inventory"])

            if libvirt_mac.lower() in map(
                lambda interface: interface["mac_address"].lower(),
                inventory["interfaces"],
            ):
                added_hosts.append({"id": host["id"], "role": libvirt_metadata["role"]})

    assert len(libvirt_nodes) == len(
        added_hosts
    ), "All nodes should have matching inventory hosts"
    client.set_hosts_roles(cluster_id=cluster_id, hosts_with_roles=added_hosts)


def set_cluster_vips(client, cluster_id):
    cluster_info = client.cluster_get(cluster_id)
    api_vip, ingress_vip = _get_vips_ips()
    cluster_info.vip_dhcp_allocation = False
    cluster_info.api_vip = api_vip
    cluster_info.ingress_vip = ingress_vip
    client.update_cluster(cluster_id, cluster_info)


def set_cluster_machine_cidr(client, cluster_id, machine_cidr):
    cluster_info = client.cluster_get(cluster_id)
    cluster_info.vip_dhcp_allocation = True
    cluster_info.machine_network_cidr = machine_cidr
    client.update_cluster(cluster_id, cluster_info)


def _get_vips_ips():
    network_subnet_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(args.vm_network_cidr).network_address
        )
        + 100
    )
    ips = utils.create_ip_address_list(
        2, starting_ip_addr=str(ipaddress.ip_address(network_subnet_starting_ip))
    )
    return ips[0], ips[1]


# TODO add config file
# Converts params from args to assisted-service cluster params
def _cluster_create_params():
    params = {
        "openshift_version": args.openshift_version,
        "base_dns_domain": args.base_dns_domain,
        "cluster_network_cidr": args.cluster_network,
        "cluster_network_host_prefix": args.host_prefix,
        "service_network_cidr": args.service_network,
        "pull_secret": args.pull_secret,
        "http_proxy": args.http_proxy,
        "https_proxy": args.https_proxy,
        "no_proxy": args.no_proxy,
        "vip_dhcp_allocation": bool(args.vip_dhcp_allocation),
    }
    return params


# convert params from args to terraform tfvars
def _create_node_details(cluster_name):
    return {
        "libvirt_worker_memory": args.worker_memory,
        "libvirt_master_memory": args.master_memory,
        "worker_count": args.number_of_workers,
        "cluster_name": cluster_name,
        "cluster_domain": args.base_dns_domain,
        "machine_cidr": args.vm_network_cidr,
        "libvirt_network_name": consts.TEST_NETWORK + args.namespace,
        "libvirt_network_mtu": args.network_mtu,
        "libvirt_network_if": args.network_bridge,
        "libvirt_worker_disk": args.worker_disk,
        "libvirt_master_disk": args.master_disk,
        'libvirt_secondary_network_name': consts.TEST_SECONDARY_NETWORK + args.namespace,
        'libvirt_secondary_network_if': f's{args.network_bridge}',
        'provisioning_cidr': _get_provisioning_cidr(),
    }


def _get_provisioning_cidr():
    provisioning_cidr = IPNetwork(args.vm_network_cidr)
    provisioning_cidr += args.ns_index + consts.NAMESPACE_POOL_SIZE
    return str(provisioning_cidr)


def validate_dns(client, cluster_id):
    if not args.managed_dns_domains:
        # 'set_dns' (using dnsmasq) is invoked after nodes_flow
        return

    cluster = client.cluster_get(cluster_id)
    api_address = "api.{}.{}".format(cluster.name, cluster.base_dns_domain)
    ingress_address = "ingress.apps.{}.{}".format(cluster.name, cluster.base_dns_domain)
    log.info(
        "Validating resolvability of the following domains: %s -> %s, %s -> %s",
        api_address,
        cluster.api_vip,
        ingress_address,
        cluster.ingress_vip,
    )
    try:
        api_answers = dns.resolver.query(api_address, "A")
        ingress_answers = dns.resolver.query(ingress_address, "A")
        api_vip = str(api_answers[0])
        ingress_vip = str(ingress_answers[0])

        if api_vip != cluster.api_vip or ingress_vip != cluster.ingress_vip:
            raise Exception("DNS domains are not resolvable")

        log.info("DNS domains are resolvable")
    except Exception as e:
        log.error("Failed to resolve DNS domains")
        raise e


# Create vms from downloaded iso that will connect to assisted-service and register
# If install cluster is set , it will run install cluster command and wait till all nodes will be in installing status
def nodes_flow(client, cluster_name, cluster, image_path):
    nodes_details = _create_node_details(cluster_name)
    if cluster:
        nodes_details["cluster_inventory_id"] = cluster.id

    tf_folder = utils.get_tf_folder(cluster_name, args.namespace)
    utils.recreate_folder(tf_folder)
    copy_tree(consts.TF_TEMPLATE, tf_folder)
    tf = terraform_utils.TerraformUtils(working_dir=tf_folder)

    create_nodes_and_wait_till_registered(
        cluster_name=cluster_name,
        inventory_client=client,
        cluster=cluster,
        image_path=image_path,
        storage_path=args.storage_path,
        master_count=args.master_count,
        nodes_details=nodes_details,
        tf=tf
    )

    if client:
        cluster_info = client.cluster_get(cluster.id)
        macs = utils.get_libvirt_nodes_macs(nodes_details["libvirt_network_name"])

        if not (cluster_info.api_vip and cluster_info.ingress_vip):
            utils.wait_till_hosts_with_macs_are_in_status(
                client=client,
                cluster_id=cluster.id,
                macs=macs,
                statuses=[
                    consts.NodesStatus.INSUFFICIENT,
                    consts.NodesStatus.PENDING_FOR_INPUT,
                ],
            )

            if args.vip_dhcp_allocation:
                set_cluster_machine_cidr(client, cluster.id, args.vm_network_cidr)
            else:
                set_cluster_vips(client, cluster.id)
        else:
            log.info("VIPs already configured")

        set_hosts_roles(client, cluster.id, nodes_details["libvirt_network_name"])
        utils.wait_till_hosts_with_macs_are_in_status(
            client=client,
            cluster_id=cluster.id,
            macs=macs,
            statuses=[consts.NodesStatus.KNOWN],
        )

        if args.install_cluster:
            time.sleep(10)
            install_cluster.run_install_flow(
                client=client,
                cluster_id=cluster.id,
                kubeconfig_path=consts.DEFAULT_CLUSTER_KUBECONFIG_PATH,
                pull_secret=args.pull_secret,
                tf=tf
            )
            # Validate DNS domains resolvability
            validate_dns(client, cluster.id)


def override_ignition(client, cluster_id):
    ignition_overrides = {
        "ignition": {
            "version": "3.1.0"
        },
        "storage": {
            "files": [
                {
                    "path": "/etc/example",
                    "contents": {"source": "data:text/plain;base64,aGVscGltdHJhcHBlZGluYXN3YWdnZXJzcGVj"}
                }
            ]
        }
    }
    client.update_discovery_ignition(cluster_id, ignition_overrides)


def execute_day1_flow(cluster_name):
    client = None
    cluster = {}
    if args.managed_dns_domains:
        args.base_dns_domain = args.managed_dns_domains.split(":")[0]

    if not args.vm_network_cidr:
        net_cidr = IPNetwork('192.168.126.0/24')
        net_cidr += args.ns_index
        args.vm_network_cidr = str(net_cidr)

    if not args.network_bridge:
        args.network_bridge = f'tt{args.ns_index}'

    image_path = None

    if not args.image:
        utils.recreate_folder(consts.IMAGE_FOLDER, force_recreate=False)
        client = assisted_service_api.create_client(
            url=utils.get_assisted_service_url_by_args(args=args)
        )
        if args.cluster_id:
            cluster = client.cluster_get(cluster_id=args.cluster_id)
        else:
            cluster = client.create_cluster(
                cluster_name,
                ssh_public_key=args.ssh_key, **_cluster_create_params()
            )

        override_ignition(client, cluster.id)

        image_path = os.path.join(
            consts.IMAGE_FOLDER,
            f'{args.namespace}-installer-image.iso'
        )
        client.generate_and_download_image(
            cluster_id=cluster.id,
            image_path=image_path,
            ssh_key=args.ssh_key,
        )

    # Iso only, cluster will be up and iso downloaded but vm will not be created
    if not args.iso_only:
        try:
            nodes_flow(client, cluster_name, cluster, args.image or image_path)
        finally:
            if not image_path or args.keep_iso:
                return
            log.info('deleting iso: %s', image_path)
            os.unlink(image_path)

    return cluster.id


def main():
    cluster_name = f'{args.cluster_name or consts.CLUSTER_PREFIX}-{args.namespace}'
    log.info('Cluster name: %s', cluster_name)

    cluster_id = args.cluster_id
    if args.day1_cluster:
        cluster_id = execute_day1_flow(cluster_name)
    if args.day2_cluster:
        day2.execute_day2_flow(cluster_id, args)

    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run discovery flow")
    parser.add_argument(
        "-i", "--image", help="Run terraform with given image", type=str, default=""
    )
    parser.add_argument(
        "-n", "--master-count", help="Masters count to spawn", type=int, default=3
    )
    parser.add_argument(
        "-p",
        "--storage-path",
        help="Path to storage pool",
        type=str,
        default=consts.STORAGE_PATH,
    )
    parser.add_argument(
        "-si", "--skip-inventory", help="Node count to spawn", action="store_true"
    )
    parser.add_argument("-k", "--ssh-key", help="Path to ssh key", type=str, default="")
    parser.add_argument(
        "-md",
        "--master-disk",
        help="Master disk size in b",
        type=int,
        default=21474836480,
    )
    parser.add_argument(
        "-wd",
        "--worker-disk",
        help="Worker disk size in b",
        type=int,
        default=21474836480,
    )
    parser.add_argument(
        "-mm",
        "--master-memory",
        help="Master memory (ram) in mb",
        type=int,
        default=8192,
    )
    parser.add_argument(
        "-wm",
        "--worker-memory",
        help="Worker memory (ram) in mb",
        type=int,
        default=8192,
    )
    parser.add_argument(
        "-nw", "--number-of-workers", help="Workers count to spawn", type=int, default=0
    )
    parser.add_argument(
        "-ndw", "--number-of-day2-workers", help="Workers count to spawn", type=int, default=0
    )
    parser.add_argument(
        "-cn",
        "--cluster-network",
        help="Cluster network with cidr",
        type=str,
        default="10.128.0.0/14",
    )
    parser.add_argument(
        "-hp", "--host-prefix", help="Host prefix to use", type=int, default=23
    )
    parser.add_argument(
        "-sn",
        "--service-network",
        help="Network for services",
        type=str,
        default="172.30.0.0/16",
    )
    parser.add_argument(
        "-ps", "--pull-secret", help="Pull secret", type=str, default=""
    )
    parser.add_argument(
        "-ov", "--openshift-version", help="Openshift version", type=str, default="4.5"
    )
    parser.add_argument(
        "-bd",
        "--base-dns-domain",
        help="Base dns domain",
        type=str,
        default="redhat.com",
    )
    parser.add_argument(
        "-mD",
        "--managed-dns-domains",
        help="DNS domains that are managaed by assisted-service, format: domain_name:domain_id/provider_type.",
        type=str,
        default="",
    )
    parser.add_argument(
        "-cN", "--cluster-name", help="Cluster name", type=str, default=""
    )
    parser.add_argument(
        "-vN",
        "--vm-network-cidr",
        help="Vm network cidr",
        type=str,
    )
    parser.add_argument(
        "-nM", "--network-mtu", help="Network MTU", type=int, default=1500
    )
    parser.add_argument(
        "-in",
        "--install-cluster",
        help="Install cluster, will take latest id",
        action="store_true",
    )
    parser.add_argument(
        '-nB',
        '--network-bridge',
        help='Network bridge to use',
        type=str,
        required=False
    )
    parser.add_argument(
        "-iO",
        "--iso-only",
        help="Create cluster and download iso, no need to spawn cluster",
        action="store_true",
    )
    parser.add_argument(
        "-pX",
        "--http-proxy",
        help="A proxy URL to use for creating HTTP connections outside the cluster",
        type=str,
        default="",
    )
    parser.add_argument(
        "-sX",
        "--https-proxy",
        help="A proxy URL to use for creating HTTPS connections outside the cluster",
        type=str,
        default="",
    )
    parser.add_argument(
        "-nX",
        "--no-proxy",
        help="A comma-separated list of destination domain names, domains, IP addresses, "
             "or other network CIDRs to exclude proxyin",
        type=str,
        default="",
    )
    parser.add_argument(
        "-iU",
        "--inventory-url",
        help="Full url of remote inventory",
        type=str,
        default="",
    )
    parser.add_argument(
        "-ns",
        "--namespace",
        help="Namespace to use",
        type=str,
        default="assisted-installer",
    )
    parser.add_argument(
        "-id", "--cluster-id", help="Cluster id to install", type=str, default=None
    )
    parser.add_argument(
        '--service-name',
        help='Override assisted-service target service name',
        type=str,
        default='assisted-service'
    )
    parser.add_argument(
        "--vip-dhcp-allocation",
        type=distutils.util.strtobool,
        nargs='?',
        const=True,
        default=True,
        help="VIP DHCP allocation mode"
    )
    parser.add_argument(
        '--ns-index',
        help='Namespace index',
        type=int,
        required=True
    )
    parser.add_argument(
        '--profile',
        help='Minikube profile for assisted-installer deployment',
        type=str,
        default='assisted-installer'
    )
    parser.add_argument(
        '--keep-iso',
        help='If set, do not delete generated iso at the end of discovery',
        action='store_true',
        default=False
    )
    parser.add_argument(
        "--day2-cluster",
        help="day2 cluster",
        action="store_true",
    )
    parser.add_argument(
        "--day1-cluster",
        help="day1 cluster",
        action="store_true",
    )
    parser.add_argument(
        "-avd", "--api-vip-dnsname",
        help="api vip dns name",
        type=str
    )
    parser.add_argument(
        "-avi", "--api-vip-ip",
        help="api vip ip",
        type=str
    )
    parser.add_argument(
        '--deploy-target',
        help='Where assisted-service is deployed',
        type=str,
        default='minikube'
    )
    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    if not args.pull_secret and args.install_cluster:
        raise Exception("Can't install cluster without pull secret, please provide one")
    main()
