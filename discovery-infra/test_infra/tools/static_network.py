import json
import os
import random
import yaml
from ipaddress import ip_network, ip_address

from test_infra import consts, utils


def generate_macs(count):
    return ["02:00:00:%02x:%02x:%02x" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for _ in range(count)]


def generate_static_network_data_from_tf(tf_folder):
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    network_config = []

    for count in range(tfvars['master_count']):
        host_data = _prepare_host_static_network_data(tfvars['libvirt_master_macs'][count],
                                                      tfvars['libvirt_secondary_master_macs'][count],
                                                      tfvars['machine_cidr_addresses'],
                                                      tfvars['provisioning_cidr_addresses'],
                                                      count)
        network_config.append(host_data)

    for count in range(tfvars['worker_count']):
        host_data = _prepare_host_static_network_data(tfvars['libvirt_worker_macs'][count], 
                                                      tfvars['libvirt_secondary_worker_macs'][count],
                                                      tfvars['machine_cidr_addresses'],
                                                      tfvars['provisioning_cidr_addresses'],
                                                      tfvars['master_count'] + count)
        network_config.append(host_data)

    return network_config


def _prepare_host_static_network_data(primary_mac,
                                      secondary_mac,
                                      machine_cidrs,
                                      provisioning_cidrs,
                                      count):
    interfaces = _prepare_interfaces(primary_mac, secondary_mac, machine_cidrs, provisioning_cidrs, count)
    dns_resolver = _prepare_dns_resolver(machine_cidrs)
    routes = _prepare_routes(primary_mac, machine_cidrs)

    host_network_config = {'interfaces': interfaces,
                           'dns-resolver': dns_resolver,
                           'routes': routes}

    return yaml.dump(host_network_config)


def _prepare_interfaces(primary_mac, secondary_mac, machine_cidrs, provisioning_cidrs, count):
    primary_interface = _prepare_interface(primary_mac, machine_cidrs, count)
    secondary_interface = _prepare_interface(secondary_mac, provisioning_cidrs, count)
    return [primary_interface, secondary_interface]

def _prepare_interface(mac, cidrs, host_count):
    ipv4_dict = {}
    ipv6_dict = {}

    ipv6_version, ip_dict = _prepare_ip_dict(cidrs[0], host_count)

    if not ipv6_version:
        ipv4_dict = ip_dict
    else:
        ipv6_dict = ip_dict

    if not ipv6_version and len(cidrs) > 1:
        _, ipv6_dict = _prepare_ip_dict(cidrs[1], host_count)

    interface = {'name': mac.replace(':', ''),
                 'type': 'ethernet',
                 'state': 'up'}
    if ipv4_dict:
        interface['ipv4'] = ipv4_dict
    if ipv6_dict:
        interface['ipv6'] = ipv6_dict

    return interface


def _prepare_ip_dict(cidr, host_count):
    network = ip_network(cidr)
    ip = str(ip_address(network.network_address) + 30 + host_count)
    return network.version == 6, {'enabled': True, 'address': [{'ip': ip, 'prefix-length': network.prefixlen}], 'dhcp': False}


def _prepare_dns_resolver(machine_cidrs):
    network = ip_network(machine_cidrs[0])
    dns_ip = str(ip_address(network.network_address) + 1)
    return {'config': {'server': [dns_ip]}}


def _prepare_routes(primary_mac, machine_cidrs):
    network = ip_network(machine_cidrs[0])
    gw_ip = str(ip_address(network.network_address) + 1)
    default_route = '::/0' if network.version == 6 else '0.0.0.0/0'
    return {'config': [{'destination': default_route , 'next-hop-address': gw_ip, 'next-hop-interface': primary_mac.replace(':', ''), 'table-id': 254}]}
