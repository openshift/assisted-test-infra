import json
import os
import random
from ipaddress import ip_address, ip_network
from typing import Any, Dict, List, Tuple

import yaml
from test_infra import consts

_PRIMARY_LOGICAL_INTERFACE = "eth0"
_SECONDARY_LOGICAL_INTERFACE = "eth1"


def generate_macs(count: int) -> List[str]:
    return [
        "02:00:00:%02x:%02x:%02x" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        for _ in range(count)
    ]


def generate_day2_static_network_data_from_tf(tf_folder: str, num_day2_workers: int) -> List[Dict[str, List[dict]]]:
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    network_config = []
    primary_macs = tfvars["libvirt_worker_macs"][len(tfvars["libvirt_worker_macs"]) - num_day2_workers:]
    secondary_macs = tfvars["libvirt_secondary_worker_macs"][
        len(tfvars["libvirt_secondary_worker_macs"]) - num_day2_workers:
    ]
    for count in range(num_day2_workers):
        host_data = _prepare_host_static_network_data(
            primary_macs[count],
            secondary_macs[count],
            tfvars["machine_cidr_addresses"],
            tfvars["provisioning_cidr_addresses"],
            tfvars["master_count"] + tfvars["worker_count"] - num_day2_workers,
        )
        network_config.append(host_data)

    return network_config


def generate_static_network_data_from_tf(tf_folder: str) -> List[Dict[str, List[dict]]]:
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    network_config = []

    for count in range(tfvars["master_count"]):
        host_data = _prepare_host_static_network_data(
            tfvars["libvirt_master_macs"][count],
            tfvars["libvirt_secondary_master_macs"][count],
            tfvars["machine_cidr_addresses"],
            tfvars["provisioning_cidr_addresses"],
            count,
        )
        network_config.append(host_data)

    for count in range(tfvars["worker_count"]):
        host_data = _prepare_host_static_network_data(
            tfvars["libvirt_worker_macs"][count],
            tfvars["libvirt_secondary_worker_macs"][count],
            tfvars["machine_cidr_addresses"],
            tfvars["provisioning_cidr_addresses"],
            tfvars["master_count"] + count,
        )
        network_config.append(host_data)

    return network_config


def _prepare_host_static_network_data(
    primary_mac: str, secondary_mac: str, machine_cidrs: List[str], provisioning_cidrs: List[str], count: int
) -> Dict[str, List[dict]]:
    interfaces = _prepare_interfaces(machine_cidrs, provisioning_cidrs, count)
    dns_resolver = _prepare_dns_resolver(machine_cidrs)
    routes = _prepare_routes(machine_cidrs)

    host_network_config = {"interfaces": interfaces, "dns-resolver": dns_resolver, "routes": routes}

    mac_interface_map = [
        {"mac_address": primary_mac, "logical_nic_name": _PRIMARY_LOGICAL_INTERFACE},
        {"mac_address": secondary_mac, "logical_nic_name": _SECONDARY_LOGICAL_INTERFACE},
    ]
    return {"network_yaml": yaml.dump(host_network_config), "mac_interface_map": mac_interface_map}


def _prepare_interfaces(machine_cidrs: List[str], provisioning_cidrs: List[str], count: int) -> List[Dict[str, str]]:
    primary_interface = _prepare_interface(_PRIMARY_LOGICAL_INTERFACE, machine_cidrs, count)
    secondary_interface = _prepare_interface(_SECONDARY_LOGICAL_INTERFACE, provisioning_cidrs, count)
    return [primary_interface, secondary_interface]


def _prepare_interface(logical_interface: str, cidrs: List[str], host_count: int) -> Dict[str, str]:
    ipv4_dict = {}
    ipv6_dict = {}

    ipv6_version, ip_dict = _prepare_ip_dict(cidrs[0], host_count)

    if not ipv6_version:
        ipv4_dict = ip_dict
    else:
        ipv6_dict = ip_dict

    if not ipv6_version and len(cidrs) > 1:
        _, ipv6_dict = _prepare_ip_dict(cidrs[1], host_count)

    interface = {"name": logical_interface, "type": "ethernet", "state": "up"}
    if ipv4_dict:
        interface["ipv4"] = ipv4_dict
    if ipv6_dict:
        interface["ipv6"] = ipv6_dict

    return interface


def _prepare_ip_dict(cidr: str, host_count: int) -> Tuple[bool, Dict[str, Any]]:
    network = ip_network(cidr)
    ip = str(ip_address(network.network_address) + 30 + host_count)
    return network.version == 6, {
        "enabled": True,
        "address": [{"ip": ip, "prefix-length": network.prefixlen}],
        "dhcp": False,
    }


def _prepare_dns_resolver(machine_cidrs: List[str]) -> Dict[str, Dict[str, List[str]]]:
    network = ip_network(machine_cidrs[0])
    dns_ip = str(ip_address(network.network_address) + 1)
    return {"config": {"server": [dns_ip]}}


def _prepare_routes(machine_cidrs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    network = ip_network(machine_cidrs[0])
    gw_ip = str(ip_address(network.network_address) + 1)
    default_route = "::/0" if network.version == 6 else "0.0.0.0/0"
    return {
        "config": [
            {
                "destination": default_route,
                "next-hop-address": gw_ip,
                "next-hop-interface": _PRIMARY_LOGICAL_INTERFACE,
                "table-id": 254,
            }
        ]
    }
