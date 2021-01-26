#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import dns.resolver
import ipaddress
import json
import os
import time
import distutils.util
from netaddr import IPNetwork, IPAddress

from test_infra import assisted_service_api, consts, utils
from test_infra.helper_classes import cluster as helper_cluster
import install_cluster
import oc_utils
import day2
from logger import log
from test_infra.utils import config_etc_hosts
from test_infra.tools import terraform_utils
from test_infra.tools import static_ips
import bootstrap_in_place as ibip


class MachineNetwork(object):
    YES_VALUES = ['yes', 'true', 'y']

    def __init__(self, ip_v4, ip_v6, machine_cidr_4, machine_cidr_6, ns_index):
        self.has_ip_v4 = ip_v4.lower() in MachineNetwork.YES_VALUES
        self.has_ip_v6 = ip_v6.lower() in MachineNetwork.YES_VALUES

        if not (self.has_ip_v4 or self.has_ip_v6):
            raise Exception("At least one of IPv4 or IPv6 must be enabled")

        self.cidr_v4 = machine_cidr_4
        self.cidr_v6 = machine_cidr_6
        self.provisioning_cidr_v4 = _get_provisioning_cidr(machine_cidr_4, ns_index)
        self.provisioning_cidr_v6 = _get_provisioning_cidr6(machine_cidr_6, ns_index)

def set_tf_config(cluster_name):
    nodes_details = _create_node_details(cluster_name)
    tf_folder = utils.get_tf_folder(cluster_name, args.namespace)
    utils.recreate_folder(tf_folder)

    utils.copy_template_tree(tf_folder, is_none_platform_mode())

    machine_net = MachineNetwork(args.ipv4, args.ipv6, args.vm_network_cidr, args.vm_network_cidr6, args.ns_index)
    default_image_path = os.path.join(consts.IMAGE_FOLDER, f'{args.namespace}-installer-image.iso')
    fill_tfvars(
        image_path=args.image or default_image_path,
        storage_path=args.storage_path,
        master_count=args.master_count,
        nodes_details=nodes_details,
        tf_folder=tf_folder,
        machine_net=machine_net
    )


# Filling tfvars json files with terraform needed variables to spawn vms
def fill_tfvars(
        image_path,
        storage_path,
        master_count,
        nodes_details,
        tf_folder,
        machine_net
):
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    master_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(machine_net.cidr_v4).network_address
        )
        + 10
    )
    worker_starting_ip = str(
        ipaddress.ip_address(
            ipaddress.IPv4Network(machine_net.cidr_v4).network_address
        )
        + 10
        + int(tfvars["master_count"])
    )
    master_count = min(master_count, consts.NUMBER_OF_MASTERS)
    worker_count = nodes_details['worker_count']
    tfvars['image_path'] = image_path
    tfvars['master_count'] = master_count
    if machine_net.has_ip_v4:
        tfvars['libvirt_master_ips'] = utils.create_ip_address_nested_list(
            master_count, starting_ip_addr=master_starting_ip
        )
        tfvars['libvirt_worker_ips'] = utils.create_ip_address_nested_list(
            worker_count, starting_ip_addr=worker_starting_ip
        )
    else:
        tfvars['libvirt_master_ips'] = utils.create_empty_nested_list(master_count)
        tfvars['libvirt_worker_ips'] = utils.create_empty_nested_list(worker_count)

    machine_cidr_addresses = []
    provisioning_cidr_addresses = []

    if machine_net.has_ip_v4:
        machine_cidr_addresses += [machine_net.cidr_v4]
        provisioning_cidr_addresses += [machine_net.provisioning_cidr_v4]

    if machine_net.has_ip_v6:
        machine_cidr_addresses += [machine_net.cidr_v6]
        provisioning_cidr_addresses += [machine_net.provisioning_cidr_v6]

    tfvars['machine_cidr_addresses'] = machine_cidr_addresses
    tfvars['provisioning_cidr_addresses'] = provisioning_cidr_addresses
    tfvars['api_vip'] = _get_vips_ips(machine_net)[0]
    tfvars['libvirt_storage_pool_path'] = storage_path
    tfvars['libvirt_master_macs'] = static_ips.generate_macs(master_count)
    tfvars['libvirt_worker_macs'] = static_ips.generate_macs(worker_count)
    tfvars.update(nodes_details)

    tfvars.update(_secondary_tfvars(master_count, nodes_details, machine_net))

    with open(tfvars_json_file, "w") as _file:
        json.dump(tfvars, _file)


def _secondary_tfvars(master_count, nodes_details, machine_net):
    vars_dict = {}
    vars_dict['libvirt_secondary_master_macs'] = static_ips.generate_macs(master_count)
    if machine_net.has_ip_v4:
        secondary_master_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(machine_net.provisioning_cidr_v4).network_address
            )
            + 10
        )
        secondary_worker_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(machine_net.provisioning_cidr_v4).network_address
            )
            + 10
            + int(master_count)
        )
    else:
        secondary_master_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv6Network(machine_net.provisioning_cidr_v6).network_address
            )
            + 16
        )
        secondary_worker_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv6Network(machine_net.provisioning_cidr_v6).network_address
            )
            + 16
            + int(master_count)
        )

    worker_count = nodes_details['worker_count']
    vars_dict['libvirt_secondary_worker_macs'] = static_ips.generate_macs(worker_count)
    if machine_net.has_ip_v4:
        vars_dict['libvirt_secondary_master_ips'] = utils.create_ip_address_nested_list(
                master_count,
                starting_ip_addr=secondary_master_starting_ip
                )
        vars_dict['libvirt_secondary_worker_ips'] = utils.create_ip_address_nested_list(
                worker_count,
                starting_ip_addr=secondary_worker_starting_ip
                )
    else:
        vars_dict['libvirt_secondary_master_ips'] = utils.create_empty_nested_list(master_count)
        vars_dict['libvirt_secondary_worker_ips'] = utils.create_empty_nested_list(worker_count)
    return vars_dict


# Run make run terraform -> creates vms
def create_nodes(
        tf
):
    log.info('Start running terraform')
    with utils.file_lock_context():
        return tf.apply()


# Starts terraform nodes creation, waits till all nodes will get ip and will move to known status
def create_nodes_and_wait_till_registered(
        inventory_client,
        cluster,
        nodes_details,
        tf
):
    nodes_count = nodes_details['master_count'] + nodes_details["worker_count"]
    create_nodes(
        tf=tf
    )

    # TODO: Check for only new nodes
    if not inventory_client:
        # We will wait for leases only if only nodes are created without connection to s
        utils.wait_till_nodes_are_ready(
            nodes_count=nodes_count, network_name=nodes_details["libvirt_network_name"]
        )
        log.info("No inventory url, will not wait till nodes registration")
        return

    log.info("Wait till nodes will be registered")

    # In case there is assisted service connection, registration to the cluster in the assisted service
    # is checked, and not relying on libvirt leases.  This overcomes bug in libvirt that does not report
    # all DHCP leases.
    statuses = [
        consts.NodesStatus.INSUFFICIENT,
        consts.NodesStatus.PENDING_FOR_INPUT,
    ]
    if nodes_details['master_count'] == 1 or is_none_platform_mode():
        statuses.append(consts.NodesStatus.KNOWN)

    utils.wait_till_all_hosts_are_in_status(
        client=inventory_client,
        cluster_id=cluster.id,
        nodes_count=nodes_count,
        statuses=statuses)


def set_cluster_vips(client, cluster_id, machine_net):
    cluster_info = client.cluster_get(cluster_id)
    api_vip, ingress_vip = _get_vips_ips(machine_net)
    cluster_info.vip_dhcp_allocation = False
    cluster_info.api_vip = api_vip
    cluster_info.ingress_vip = ingress_vip
    client.update_cluster(cluster_id, cluster_info)


def set_cluster_machine_cidr(client, cluster_id, machine_net, set_vip_dhcp_allocation=True):
    cluster_info = client.cluster_get(cluster_id)
    if set_vip_dhcp_allocation:
        cluster_info.vip_dhcp_allocation = True
    cluster_info.machine_network_cidr = machine_net.cidr_v6 if machine_net.has_ip_v6 and not machine_net.has_ip_v4 else machine_net.cidr_v4
    client.update_cluster(cluster_id, cluster_info)

def _get_vips_ips(machine_net):
    if machine_net.has_ip_v4:
        network_subnet_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv4Network(machine_net.cidr_v4).network_address
            )
            + 100
        )
    else:
        network_subnet_starting_ip = str(
            ipaddress.ip_address(
                ipaddress.IPv6Network(machine_net.cidr_v6).network_address
            )
            + 100
        )
    ips = utils.create_ip_address_list(
        2, starting_ip_addr=str(ipaddress.ip_address(network_subnet_starting_ip))
    )
    return ips[0], ips[1]


def _get_host_ip_from_cidr(cidr):
    return str(IPNetwork(cidr).ip + 1)

def _get_proxy_ip(cidr):
    return IPNetwork(cidr).ip + 1

def _get_http_proxy_params(ipv4, ipv6):
    if args.proxy:
        ipv6Only = ipv6 and not ipv4
        if ipv6Only:
            proxy_ip = _get_proxy_ip(args.vm_network_cidr6)
            proxy_url = f'http://[{proxy_ip}]:3128'
            no_proxy = ','.join([args.vm_network_cidr6, args.service_network6, args.cluster_network6,
                                 consts.DEFAULT_TEST_INFRA_DOMAIN])
        else:
            proxy_ip = _get_proxy_ip(args.vm_network_cidr)
            proxy_url = f'http://{proxy_ip}:3128'
            no_proxy = ','.join([args.vm_network_cidr, args.service_network, args.cluster_network,
                                 consts.DEFAULT_TEST_INFRA_DOMAIN])
        return proxy_url, proxy_url, no_proxy
    else:
        return args.http_proxy, args.https_proxy, args.no_proxy



# TODO add config file
# Converts params from args to assisted-service cluster params
def _cluster_create_params():
    ipv4 = args.ipv4 and args.ipv4.lower() in MachineNetwork.YES_VALUES
    ipv6 = args.ipv6 and args.ipv6.lower() in MachineNetwork.YES_VALUES
    ntp_source = _get_host_ip_from_cidr(args.vm_network_cidr6 if ipv6 and not ipv4 else args.vm_network_cidr)
    user_managed_networking = is_user_managed_networking()
    http_proxy, https_proxy, no_proxy = _get_http_proxy_params(ipv4=ipv4, ipv6=ipv6)
    params = {
        "openshift_version": utils.get_openshift_version(),
        "base_dns_domain": args.base_dns_domain,
        "cluster_network_cidr": args.cluster_network if ipv4 else args.cluster_network6,
        "cluster_network_host_prefix": args.host_prefix if ipv4 else args.host_prefix6,
        "service_network_cidr": args.service_network if ipv4 else args.service_network6,
        "pull_secret": args.pull_secret,
        "http_proxy": http_proxy,
        "https_proxy": https_proxy,
        "no_proxy": no_proxy,
        "vip_dhcp_allocation": bool(args.vip_dhcp_allocation) and not user_managed_networking,
        "additional_ntp_source": ntp_source,
        "user_managed_networking": user_managed_networking,
        "high_availability_mode": "None" if args.master_count == 1 else "Full"
    }
    return params


# convert params from args to terraform tfvars
def _create_node_details(cluster_name):
    return {
        "libvirt_worker_memory": args.worker_memory,
        "libvirt_master_memory": args.master_memory if not args.master_count == 1 else args.master_memory * 2,
        "worker_count": args.number_of_workers,
        "cluster_name": cluster_name,
        "cluster_domain": args.base_dns_domain,
        "libvirt_network_name": consts.TEST_NETWORK + args.namespace,
        "libvirt_network_mtu": args.network_mtu,
        "libvirt_network_if": args.network_bridge,
        "libvirt_worker_disk": args.worker_disk,
        "libvirt_master_disk": args.master_disk,
        "libvirt_secondary_network_name": consts.TEST_SECONDARY_NETWORK + args.namespace,
        "libvirt_secondary_network_if": f's{args.network_bridge}',
        "bootstrap_in_place": args.master_count == 1,
    }


def _get_provisioning_cidr(cidr, ns_index):
    provisioning_cidr = IPNetwork(cidr)
    provisioning_cidr += ns_index + consts.NAMESPACE_POOL_SIZE
    return str(provisioning_cidr)


def _get_provisioning_cidr6(cidr, ns_index):
    provisioning_cidr = IPNetwork(cidr)
    provisioning_cidr += ns_index
    for _ in range(4):
        provisioning_cidr += (1 << 63)
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
def nodes_flow(client, cluster_name, cluster):
    tf_folder = utils.get_tf_folder(cluster_name, args.namespace)
    nodes_details = utils.get_tfvars(tf_folder)
    if cluster:
        nodes_details["cluster_inventory_id"] = cluster.id
        utils.set_tfvars(tf_folder, nodes_details)

    tf = terraform_utils.TerraformUtils(working_dir=tf_folder)
    machine_net = MachineNetwork(args.ipv4, args.ipv6, args.vm_network_cidr, args.vm_network_cidr6, args.ns_index)

    create_nodes_and_wait_till_registered(
        inventory_client=client,
        cluster=cluster,
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
                    consts.NodesStatus.KNOWN
                ],
            )

            if args.master_count == 1:
                is_ip4 =  machine_net.has_ip_v4 or not machine_net.has_ip_v6
                set_cluster_machine_cidr(client, cluster.id, machine_net, set_vip_dhcp_allocation=False)
                cidr = args.vm_network_cidr if is_ip4 else args.vm_network_cidr6
                tf.change_variables({"single_node_ip": helper_cluster.Cluster.get_ip_for_single_node(client, cluster.id, cidr, ipv4_first=is_ip4)})
            elif args.vip_dhcp_allocation:
                set_cluster_machine_cidr(client, cluster.id, machine_net)
            else:
                set_cluster_vips(client, cluster.id, machine_net)
        else:
            log.info("VIPs already configured")

        set_hosts_roles(client, cluster, nodes_details, machine_net, tf, args.master_count, args.with_static_ips)

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
            if args.wait_for_cvo:
                cluster_info = client.cluster_get(cluster.id)
                log.info("Start waiting till CVO status is available")
                api_vip = helper_cluster.get_api_vip_from_cluster(client, cluster_info)
                config_etc_hosts(cluster_info.name, cluster_info.base_dns_domain, api_vip)
                utils.wait_for_cvo_available()


def set_hosts_roles(client, cluster, nodes_details, machine_net, tf, master_count, static_ip_mode):

    networks_names = (
        nodes_details["libvirt_network_name"],
        nodes_details["libvirt_secondary_network_name"]
    )

    # don't set roles in bip role
    if machine_net.has_ip_v4:
        libvirt_nodes = utils.get_libvirt_nodes_mac_role_ip_and_name(networks_names[0])
        libvirt_nodes.update(utils.get_libvirt_nodes_mac_role_ip_and_name(networks_names[1]))
        if static_ip_mode:
            log.info("Setting hostnames when running in static ips mode")
            update_hostnames = True
        else:
            update_hostnames = False
    else:
        log.warning("Work around libvirt for Terrafrom not setting hostnames of IPv6-only hosts")
        libvirt_nodes = utils.get_libvirt_nodes_from_tf_state(networks_names, tf.get_state())
        update_hostnames = True

    utils.update_hosts(client, cluster.id, libvirt_nodes, update_hostnames=update_hostnames,
                       update_roles=master_count > 1)


def execute_day1_flow(cluster_name):
    client = None
    cluster = {}
    if args.managed_dns_domains:
        args.base_dns_domain = args.managed_dns_domains.split(":")[0]

    if not args.vm_network_cidr:
        net_cidr = IPNetwork('192.168.126.0/24')
        net_cidr += args.ns_index
        args.vm_network_cidr = str(net_cidr)

    if not args.vm_network_cidr6:
        net_cidr = IPNetwork('1001:db8::/120')
        net_cidr += args.ns_index
        args.vm_network_cidr6 = str(net_cidr)

    if not args.network_bridge:
        args.network_bridge = f'tt{args.ns_index}'

    set_tf_config(cluster_name)
    image_path = None
    image_type = args.iso_image_type

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

        image_path = os.path.join(
            consts.IMAGE_FOLDER,
            f'{args.namespace}-installer-image.iso'
        )

        if args.with_static_ips:
            tf_folder = utils.get_tf_folder(cluster_name, args.namespace)
            static_ips_config = static_ips.generate_static_ips_data_from_tf(tf_folder)
        else:
            static_ips_config = None

        client.generate_and_download_image(
            cluster_id=cluster.id,
            image_path=image_path,
            image_type=image_type,
            ssh_key=args.ssh_key,
            static_ips=static_ips_config,
        )

    # Iso only, cluster will be up and iso downloaded but vm will not be created
    if not args.iso_only:
        try:
            nodes_flow(client, cluster_name, cluster)
        finally:
            if not image_path or args.keep_iso:
                return
            log.info('deleting iso: %s', image_path)
            os.unlink(image_path)

    return cluster.id


def is_user_managed_networking():
    return is_none_platform_mode() or args.master_count == 1


def is_none_platform_mode():
    return args.platform.lower() == consts.Platforms.NONE


def main():
    cluster_name = f'{args.cluster_name or consts.CLUSTER_PREFIX}-{args.namespace}'
    log.info('Cluster name: %s', cluster_name)

    cluster_id = args.cluster_id
    if args.day1_cluster:
        cluster_id = execute_day1_flow(cluster_name)

    # None platform currently not supporting day2
    if is_none_platform_mode():
        return

    if args.day2_cloud_cluster:
        day2.execute_day2_cloud_flow(cluster_id, args)
    if args.day2_ocp_cluster:
        day2.execute_day2_ocp_flow(cluster_id, args)
    if args.bootstrap_in_place:
        ibip.execute_ibip_flow(args)


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
        "-cn6",
        "--cluster-network6",
        help="Cluster network with cidr",
        type=str,
        default="2002:db8::/53",
    )
    parser.add_argument(
        "-hp", "--host-prefix", help="Host prefix to use", type=int, default=23
    )
    parser.add_argument(
        "-hp6", "--host-prefix6", help="Host prefix to use", type=int, default=64
    )
    parser.add_argument(
        "-sn",
        "--service-network",
        help="Network for services",
        type=str,
        default="172.30.0.0/16",
    )
    parser.add_argument(
        "-sn6",
        "--service-network6",
        help="Network for services",
        type=str,
        default="2003:db8::/112",
    )
    parser.add_argument(
        "-ps", "--pull-secret", help="Pull secret", type=str, default=""
    )
    parser.add_argument(
        "--with-static-ips",
        help="Static ips mode",
        action="store_true",
    )
    parser.add_argument(
        "--iso-image-type",
        help="ISO image type (full-iso/minimal-iso)",
        type=str,
        default=consts.ImageType.FULL_ISO,
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
        help="Vm network cidr for IPv4",
        type=str,
        default='192.168.126.0/24'
    )
    parser.add_argument(
        "-vN6",
        "--vm-network-cidr6",
        help="Vm network cidr for IPv6",
        type=str,
        default='1001:db8::/120'
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
        "-cvo",
        "--wait-for-cvo",
        help="Wait for CVO available after cluster installation",
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
        "--day2-cloud-cluster",
        help="day2 cloud cluster",
        action="store_true",
    )
    parser.add_argument(
        "--day2-ocp-cluster",
        help="day2 ocp cluster",
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
    parser.add_argument(
        "--ipv4",
        help='Should IPv4 be installed',
        type=str,
        default='yes'
    )
    parser.add_argument(
        "--ipv6",
        help='Should IPv6 be installed',
        type=str,
        default=''
    )
    parser.add_argument(
        '--platform',
        help='VMs platform mode (\'baremetal\' or \'none\')',
        type=str,
        default='baremetal'
    )
    parser.add_argument(
        "--bootstrap-in-place",
        help="single node cluster with bootstrap in place flow",
        action="store_true",
    )
    parser.add_argument(
        "--proxy",
        help="use http proxy with default values",
        type=distutils.util.strtobool,
        nargs='?',
        const=True,
        default=False,
    )

    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    if not args.pull_secret:
        raise Exception("Can't install cluster without pull secret, please provide one")

    if args.master_count == 1:
        log.info("Master count is 1, setting workers to 0")
        args.number_of_workers = 0

    main()
