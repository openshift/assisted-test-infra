import json
import os
import random
from ipaddress import ip_address, ip_network
from typing import Any, Dict, List, Set, Tuple

import yaml

import consts
from assisted_test_infra.test_infra import BaseInfraEnvConfig

_PRIMARY_LOGICAL_INTERFACE = "eth0"
_SECONDARY_LOGICAL_INTERFACE = "eth1"


def generate_macs(count: int) -> List[str]:
    return [
        f"02:00:00:{random.randint(0, 255):02x}:{random.randint(0, 255):02x}:{random.randint(0, 255):02x}"
        for _ in range(count)
    ]


def generate_day2_static_network_data_from_tf(tf_folder: str, num_day2_workers: int) -> List[Dict[str, List[dict]]]:
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    network_config = []
    primary_macs = tfvars["libvirt_worker_macs"][len(tfvars["libvirt_worker_macs"]) - num_day2_workers :]
    secondary_macs = tfvars["libvirt_secondary_worker_macs"][
        len(tfvars["libvirt_secondary_worker_macs"]) - num_day2_workers :
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


def _generate_physical_static_network_data_from_tf(tfvars: Dict[str, any]) -> List[Dict[str, List[dict]]]:
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


def _generate_bonded_static_network_data_from_tf(
    tfvars: Dict[str, Any], num_bonded_slaves: int, bonding_mode: str
) -> List[Dict[str, List[dict]]]:
    network_config = []

    for count in range(tfvars["master_count"]):
        host_data = _prepare_host_bonded_static_network_data(
            tfvars["libvirt_master_macs"][num_bonded_slaves * count : num_bonded_slaves * (count + 1)],
            tfvars["libvirt_secondary_master_macs"][num_bonded_slaves * count : num_bonded_slaves * (count + 1)],
            tfvars["machine_cidr_addresses"],
            tfvars["provisioning_cidr_addresses"],
            count,
            num_bonded_slaves,
            bonding_mode,
        )
        network_config.append(host_data)

    for count in range(tfvars["worker_count"]):
        host_data = _prepare_host_bonded_static_network_data(
            tfvars["libvirt_worker_macs"][num_bonded_slaves * count : num_bonded_slaves * (count + 1)],
            tfvars["libvirt_secondary_worker_macs"][num_bonded_slaves * count : num_bonded_slaves * (count + 1)],
            tfvars["machine_cidr_addresses"],
            tfvars["provisioning_cidr_addresses"],
            tfvars["master_count"] + count,
            num_bonded_slaves,
            bonding_mode,
        )
        network_config.append(host_data)

    return network_config


def generate_static_network_data_from_tf(
    tf_folder: str, infra_env_configuration: BaseInfraEnvConfig
) -> List[Dict[str, List[dict]]]:
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    if infra_env_configuration.is_bonded:
        return _generate_bonded_static_network_data_from_tf(
            tfvars, infra_env_configuration.num_bonded_slaves, infra_env_configuration.bonding_mode
        )
    else:
        return _generate_physical_static_network_data_from_tf(tfvars)


def get_name_to_mac_addresses_mapping(tf_folder: str) -> Dict[str, Set[str]]:
    tfstate_json_file = os.path.join(tf_folder, consts.TFSTATE_FILE)
    with open(tfstate_json_file) as _file:
        tfstate = json.load(_file)
    ret = dict()
    for resource in tfstate["resources"]:
        if resource["mode"] == "managed" and resource["type"] == "libvirt_domain":
            for domain in resource["instances"]:
                attributes = domain["attributes"]
                macs = set()
                for intf in attributes["network_interface"]:
                    macs.add(intf["mac"].lower())
                ret[attributes["name"]] = macs
    return ret


def _prepare_host_static_network_data(
    primary_mac: str, secondary_mac: str, machine_cidrs: List[str], provisioning_cidrs: List[str], count: int
) -> Dict[str, List[dict]]:
    interfaces = _prepare_interfaces(machine_cidrs, provisioning_cidrs, count)
    dns_resolver = _prepare_dns_resolver(machine_cidrs)
    routes = _prepare_routes(_PRIMARY_LOGICAL_INTERFACE, machine_cidrs)

    host_network_config = {"interfaces": interfaces, "dns-resolver": dns_resolver, "routes": routes}

    mac_interface_map = [
        {"mac_address": primary_mac, "logical_nic_name": _PRIMARY_LOGICAL_INTERFACE},
        {"mac_address": secondary_mac, "logical_nic_name": _SECONDARY_LOGICAL_INTERFACE},
    ]
    return {"network_yaml": yaml.dump(host_network_config), "mac_interface_map": mac_interface_map}


def _prepare_host_bonded_static_network_data(
    primary_macs: List[str],
    secondary_macs: List[str],
    machine_cidrs: List[str],
    provisioning_cidrs: List[str],
    count: int,
    num_bonded_slaves: int,
    bonding_mode: str,
) -> Dict[str, Any]:
    interfaces = _prepare_bonded_interfaces(machine_cidrs, provisioning_cidrs, count, num_bonded_slaves, bonding_mode)
    dns_resolver = _prepare_dns_resolver(machine_cidrs)
    routes = _prepare_routes("bond0", machine_cidrs)

    host_network_config = {"interfaces": interfaces, "dns-resolver": dns_resolver, "routes": routes}

    mac_interface_map = []
    for i in range(len(primary_macs)):
        mac_interface_map.append({"mac_address": primary_macs[i], "logical_nic_name": f"eth{i}"})
    for i in range(len(secondary_macs)):
        mac_interface_map.append({"mac_address": secondary_macs[i], "logical_nic_name": f"eth{i+len(primary_macs)}"})
    return {"network_yaml": yaml.dump(host_network_config), "mac_interface_map": mac_interface_map}


def _prepare_interfaces(machine_cidrs: List[str], provisioning_cidrs: List[str], count: int) -> List[Dict[str, str]]:
    primary_interface = _prepare_interface(_PRIMARY_LOGICAL_INTERFACE, machine_cidrs, count)
    secondary_interface = _prepare_interface(_SECONDARY_LOGICAL_INTERFACE, provisioning_cidrs, count)
    return [primary_interface, secondary_interface]


def _prepare_bonded_interfaces(
    machine_cidrs: List[str], provisioning_cidrs: List[str], count: int, num_bonded_slaves: int, bonding_mode: str
) -> List[Dict[str, Any]]:
    primary_interface = _prepare_bonded_interface("bond0", 0, machine_cidrs, count, num_bonded_slaves, bonding_mode)
    secondary_interface = _prepare_bonded_interface(
        "bond1", num_bonded_slaves, provisioning_cidrs, count, num_bonded_slaves, bonding_mode
    )
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


def _prepare_bonded_interface(
    logical_interface: str,
    starting_physical_interface: int,
    cidrs: List[str],
    host_count: int,
    num_bonded_slaves: int,
    bonding_mode: str,
) -> Dict[str, Any]:
    ipv4_dict = {}
    ipv6_dict = {}

    ipv6_version, ip_dict = _prepare_ip_dict(cidrs[0], host_count)

    if not ipv6_version:
        ipv4_dict = ip_dict
    else:
        ipv6_dict = ip_dict

    if not ipv6_version and len(cidrs) > 1:
        _, ipv6_dict = _prepare_ip_dict(cidrs[1], host_count)

    interface = {
        "name": logical_interface,
        "type": "bond",
        "state": "up",
        "link-aggregation": _prepare_link_aggregation(starting_physical_interface, num_bonded_slaves, bonding_mode),
    }
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


def _prepare_link_aggregation(
    starting_physical_interface: int, num_bonded_slaves: int, bonding_mode: str
) -> Dict[str, Any]:
    return {
        "mode": bonding_mode,
        "options": {"miimon": "140"},
        "port": [f"eth{starting_physical_interface+i}" for i in range(num_bonded_slaves)],
    }


def _prepare_dns_resolver(machine_cidrs: List[str]) -> Dict[str, Dict[str, List[str]]]:
    network = ip_network(machine_cidrs[0])
    dns_ip = str(ip_address(network.network_address) + 1)
    return {"config": {"server": [dns_ip]}}


def _prepare_routes(next_hop_interface: str, machine_cidrs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    network = ip_network(machine_cidrs[0])
    gw_ip = str(ip_address(network.network_address) + 1)
    default_route = "::/0" if network.version == 6 else "0.0.0.0/0"
    return {
        "config": [
            {
                "destination": default_route,
                "next-hop-address": gw_ip,
                "next-hop-interface": next_hop_interface,
                "table-id": 254,
            }
        ]
    }
