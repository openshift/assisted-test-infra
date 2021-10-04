import json
import os
import random
from ipaddress import ip_address, ip_network
from typing import Any, Dict, List, Tuple

import yaml
from test_infra import consts

LOGICAL_INTERFACE_PREFIX = "eth"
PRIMARY_LOGICAL_INTERFACE = LOGICAL_INTERFACE_PREFIX + "0"
STATIC_IPS_PREFIX = 30


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
    macs = tfvars["libvirt_worker_macs"][len(tfvars["libvirt_worker_macs"]) - num_day2_workers:]
    for count in range(num_day2_workers):
        host_data = _prepare_host_static_network_data(
            macs[count],
            tfvars["machine_cidr_addresses"],
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
            tfvars["machine_cidr_addresses"],
            count,
        )
        network_config.append(host_data)

    for count in range(tfvars["worker_count"]):
        host_data = _prepare_host_static_network_data(
            tfvars["libvirt_worker_macs"][count],
            tfvars["machine_cidr_addresses"],
            tfvars["master_count"] + count,
        )
        network_config.append(host_data)

    return network_config


def _prepare_host_static_network_data(macs: List[str], networks: List[str], count: int) -> Dict[str, List[dict]]:
    interfaces = _prepare_interfaces(networks, count)
    dns_resolver = _prepare_dns_resolver(networks[0])
    routes = _prepare_routes(networks[0])

    host_network_config = {"interfaces": interfaces, "dns-resolver": dns_resolver, "routes": routes}
    mac_interface_map = [
        {"mac_address": mac, "logical_nic_name": f"{LOGICAL_INTERFACE_PREFIX}{idx}"}
        for idx, mac in enumerate(macs)
    ]

    return {"network_yaml": yaml.dump(host_network_config), "mac_interface_map": mac_interface_map}


def _prepare_interfaces(networks: List[str], count: int) -> List[Dict[str, str]]:
    interfaces = []
    for idx, network in enumerate(networks):
        interfaces.append(_prepare_interface(f"{LOGICAL_INTERFACE_PREFIX}{idx}", network, count))
    return interfaces


def _prepare_interface(logical_interface: str, cidr: str, host_count: int) -> Dict[str, str]:
    '''
    Creating NMState Interface. see https://nmstate.io/devel/api.html#basic-interface
    '''

    interface = {
        "name": logical_interface, 
        "type": "ethernet", 
        "state": "up"
    }
    ipv6_version, ip_dict = _prepare_ip_dict(cidr, host_count)
    if ipv6_version:
        interface["ipv6"] = ip_dict
    else:
        interface["ipv4"] = ip_dict

    return interface


def _prepare_ip_dict(cidr: str, host_count: int) -> Tuple[bool, Dict[str, Any]]:
    network = ip_network(cidr)
    ip = str(ip_address(network.network_address) + STATIC_IPS_PREFIX + host_count)
    return network.version == 6, {
        "enabled": True,
        "address": [{"ip": ip, "prefix-length": network.prefixlen}],
        "dhcp": False,
    }


def _prepare_dns_resolver(primary_cidr: str) -> Dict[str, Dict[str, List[str]]]:
    network = ip_network(primary_cidr)
    dns_ip = str(ip_address(network.network_address) + 1)
    return {"config": {"server": [dns_ip]}}


def _prepare_routes(primary_cidr: str) -> Dict[str, List[Dict[str, Any]]]:
    network = ip_network(primary_cidr)
    gw_ip = str(ip_address(network.network_address) + 1)
    default_route = "::/0" if network.version == 6 else "0.0.0.0/0"
    return {
        "config": [
            {
                "destination": default_route,
                "next-hop-address": gw_ip,
                "next-hop-interface": PRIMARY_LOGICAL_INTERFACE,
                "table-id": 254,
            }
        ]
    }
