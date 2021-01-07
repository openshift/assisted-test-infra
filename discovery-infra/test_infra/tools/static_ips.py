import ipaddress
import random

from test_infra import utils


def generate_static_ips_data(num_masters, num_workers, machine_net):
    masters_macs = _generate_macs(num_masters)
    masters_secondary_macs = _generate_macs(num_masters)
    workers_macs = []
    workers_secondary_macs = []
    if num_workers > 0:
        workers_macs = _generate_macs(num_workers)
        workers_secondary_macs = _generate_macs(num_workers)

    masters_static_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_net.cidr_v4).network_address) + 30)
    masters_static_secondary_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_net.provisioning_cidr_v4).network_address) + 30)
    workers_static_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_net.cidr_v4).network_address) + 30 + num_masters)
    workers_static_secondary_starting_ip = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_net.provisioning_cidr_v4).network_address) + 30 + num_masters)

    masters_static_ips = utils.create_ip_address_list(num_masters, masters_static_starting_ip)
    masters_static_secondary_ips = utils.create_ip_address_list(num_masters, masters_static_secondary_starting_ip)
    workers_static_ips = utils.create_ip_address_list(num_workers, workers_static_starting_ip)
    workers_static_secondary_ips = utils.create_ip_address_list(num_workers, workers_static_secondary_starting_ip)

    mask = str(ipaddress.IPv4Network(machine_net.cidr_v4).prefixlen)
    mask_secondary = str(ipaddress.IPv4Network(machine_net.provisioning_cidr_v4).prefixlen)
    gw_dns = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_net.cidr_v4).network_address) + 1)
    gw_dns_secondary = str(ipaddress.ip_address(ipaddress.IPv4Network(machine_net.provisioning_cidr_v4).network_address) + 1)

    static_ips = []
    for netdata in [(masters_macs, masters_static_ips, mask, gw_dns, num_masters),
                    (masters_secondary_macs, masters_static_secondary_ips, mask_secondary, gw_dns_secondary, num_masters),
                    (workers_macs, workers_static_ips, mask, gw_dns, num_workers),
                    (workers_secondary_macs, workers_static_secondary_ips, mask_secondary, gw_dns_secondary, num_workers)]:
        data = [{'mac': netdata[0][i], 'ip': netdata[1][i], 'mask': netdata[2], 'gateway': netdata[3], 'dns': netdata[3]} for i in range(netdata[4])]
        static_ips = static_ips + data

    return static_ips,(masters_macs, masters_secondary_macs, workers_macs, workers_secondary_macs)


def _generate_macs(count):
    return ["02:00:00:%02x:%02x:%02x" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for x in range(count)]
