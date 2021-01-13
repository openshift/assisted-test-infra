import ipaddress
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
    return _generate_static_ips_data(tfvars['machine_cidr_addresses'][0],
                                     tfvars['provisioning_cidr_addresses'][0],
                                     tfvars['libvirt_master_macs'],
                                     tfvars['libvirt_secondary_master_macs'],
                                     tfvars['libvirt_worker_macs'],
                                     tfvars['libvirt_secondary_worker_macs'])


def _generate_static_ips_data(machine_cidr,
                              provisioning_cidr,
                              masters_macs,
                              masters_secondary_macs,
                              workers_macs,
                              workers_secondary_macs):
    num_masters = len(masters_macs)
    num_workers = len(workers_macs)

    # set starting static ips
    masters_static_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_cidr).network_address) + 30)
    masters_static_secondary_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(provisioning_cidr).network_address) + 30)
    workers_static_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_cidr).network_address) + 30 + num_masters)
    workers_static_secondary_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(provisioning_cidr).network_address) + 30 + num_masters)

    # set static ips lists
    masters_static_ips = utils.create_ip_address_list(num_masters, masters_static_starting_ip)
    masters_static_secondary_ips = utils.create_ip_address_list(num_masters, masters_static_secondary_starting_ip)
    workers_static_ips = utils.create_ip_address_list(num_workers, workers_static_starting_ip)
    workers_static_secondary_ips = utils.create_ip_address_list(num_workers, workers_static_secondary_starting_ip)

    mask = str(ipaddress.IPv4Network(machine_cidr).prefixlen)
    mask_secondary = str(ipaddress.IPv4Network(provisioning_cidr).prefixlen)
    gw_dns = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_cidr).network_address) + 1)
    gw_dns_secondary = str(ipaddress.ip_address(ipaddress.IPv4Network(provisioning_cidr).network_address) + 1)

    static_ips = []
    for netdata in [(masters_macs, masters_static_ips, mask, gw_dns, num_masters),
                    (masters_secondary_macs, masters_static_secondary_ips, mask_secondary, gw_dns_secondary, num_masters),
                    (workers_macs, workers_static_ips, mask, gw_dns, num_workers),
                    (workers_secondary_macs, workers_static_secondary_ips, mask_secondary, gw_dns_secondary, num_workers)]:
        data = [{'mac': netdata[0][i], 'ip': netdata[1][i], 'mask': netdata[2], 'gateway': netdata[3], 'dns': netdata[3]} for i in range(netdata[4])]
        static_ips = static_ips + data

    return static_ips

