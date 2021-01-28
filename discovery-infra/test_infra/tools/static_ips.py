from ipaddress import ip_network, ip_address
import random
import json
import os

from test_infra import utils
from test_infra import consts


def generate_macs(count):
    return ["02:00:00:%02x:%02x:%02x" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for x in range(count)]


def generate_static_ips_data_from_tf(tf_folder):

    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)

    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    return _generate_static_ips_data(tfvars['machine_cidr_addresses'],
                                     tfvars['provisioning_cidr_addresses'],
                                     tfvars['libvirt_master_macs'],
                                     tfvars['libvirt_secondary_master_macs'],
                                     tfvars['libvirt_worker_macs'],
                                     tfvars['libvirt_secondary_worker_macs'])


def _generate_static_ips_data(machine_cidrs,
                              provisioning_cidrs,
                              masters_macs,
                              masters_secondary_macs,
                              workers_macs,
                              workers_secondary_macs):

    num_masters = len(masters_macs)

    static_ips = []

    static_ips.extend(_genetate_ips(masters_macs, machine_cidrs, 0))

    static_ips.extend(_genetate_ips(
        masters_secondary_macs, provisioning_cidrs, 0))

    static_ips.extend(_genetate_ips(workers_macs, machine_cidrs, num_masters))

    static_ips.extend(_genetate_ips(workers_secondary_macs,
                                    provisioning_cidrs, num_masters))

    return static_ips


def _genetate_ips(mac_addresses, cidrs, address_offset):

    num_nodes = len(mac_addresses)

    first_net = ip_network(cidrs[0])
    ipv4_gen = _static_conf_gen(num_nodes, first_net, address_offset) if first_net.version == 4 \
        else _empty_conf_gen()

    if first_net.version == 6:
        ipv6_gen = _static_conf_gen(num_nodes, first_net, address_offset)
    else:
        ipv6_gen = _static_conf_gen(num_nodes, ip_network(cidrs[1]), address_offset) if len(cidrs) > 1 \
            else _empty_conf_gen()

    static_ips = []
    for mac in mac_addresses:
        static_ips.append({
            'mac': mac,
            'ipv4_config': next(ipv4_gen),
            'ipv6_config': next(ipv6_gen)
        })

    return static_ips


def _static_conf_gen(num_nodes, network, address_offset=0):
    starting_ip = str(ip_address(network.network_address)
                      + 30 + address_offset)
    ips = utils.create_ip_address_list(num_nodes, starting_ip)
    mask = str(network.prefixlen)
    gw_dns = str(ip_address(network.network_address) + 1)

    for i in range(num_nodes):
        yield {'ip': ips[i], 'gateway': gw_dns, 'dns': gw_dns, 'mask':mask}


def _empty_conf_gen():
    return iter(lambda: {}, 1)
