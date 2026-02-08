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


def _generate_bonded_static_network_data_from_tf(
    tfvars: Dict[str, Any],
    num_bonded_slaves: int,
    bonding_mode: str,
    *,
    vlan_enabled: bool,
    vlan_id: int,
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
            vlan_enabled=vlan_enabled,
            vlan_id=vlan_id,
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
            vlan_enabled=vlan_enabled,
            vlan_id=vlan_id,
        )
        network_config.append(host_data)

    return network_config


def generate_static_network_data_from_tf(
    tf_folder: str, infra_env_configuration: BaseInfraEnvConfig
) -> List[Dict[str, List[dict]]]:
    tfvars_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tfvars_json_file) as _file:
        tfvars = json.load(_file)

    vlan_enabled = bool(getattr(infra_env_configuration, "static_ips_vlan", False))
    vlan_id = int(getattr(infra_env_configuration, "vlan_id", 100) or 100)

    if infra_env_configuration.is_bonded:
        return _generate_bonded_static_network_data_from_tf(
            tfvars,
            infra_env_configuration.num_bonded_slaves,
            infra_env_configuration.bonding_mode,
            vlan_enabled=vlan_enabled,
            vlan_id=vlan_id,
        )
    else:
        # Thread VLAN flags through the physical generator via closures or by post-processing below
        network_config = []
        for count in range(tfvars["master_count"]):
            host_data = _prepare_host_static_network_data(
                tfvars["libvirt_master_macs"][count],
                tfvars["libvirt_secondary_master_macs"][count],
                tfvars["machine_cidr_addresses"],
                tfvars["provisioning_cidr_addresses"],
                count,
                vlan_enabled=vlan_enabled,
                vlan_id=vlan_id,
            )
            network_config.append(host_data)

        for count in range(tfvars["worker_count"]):
            host_data = _prepare_host_static_network_data(
                tfvars["libvirt_worker_macs"][count],
                tfvars["libvirt_secondary_worker_macs"][count],
                tfvars["machine_cidr_addresses"],
                tfvars["provisioning_cidr_addresses"],
                tfvars["master_count"] + count,
                vlan_enabled=vlan_enabled,
                vlan_id=vlan_id,
            )
            network_config.append(host_data)

        return network_config


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
    primary_mac: str,
    secondary_mac: str,
    machine_cidrs: List[str],
    provisioning_cidrs: List[str],
    count: int,
    *,
    vlan_enabled: bool,
    vlan_id: int,
) -> Dict[str, List[dict]]:
    interfaces = _prepare_interfaces(
        machine_cidrs, provisioning_cidrs, count, vlan_enabled=vlan_enabled, vlan_id=vlan_id
    )
    dns_resolver = _prepare_dns_resolver(machine_cidrs, vlan_enabled=vlan_enabled)
    next_hop_iface = f"{_PRIMARY_LOGICAL_INTERFACE}.{vlan_id}" if vlan_enabled else _PRIMARY_LOGICAL_INTERFACE
    routes = _prepare_routes(next_hop_iface, machine_cidrs)

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
    *,
    vlan_enabled: bool,
    vlan_id: int,
) -> Dict[str, Any]:
    interfaces = _prepare_bonded_interfaces(
        machine_cidrs,
        provisioning_cidrs,
        count,
        num_bonded_slaves,
        bonding_mode,
        vlan_enabled=vlan_enabled,
        vlan_id=vlan_id,
    )
    dns_resolver = _prepare_dns_resolver(machine_cidrs, vlan_enabled=vlan_enabled)
    next_hop_iface = f"bond0.{vlan_id}" if vlan_enabled else "bond0"
    routes = _prepare_routes(next_hop_iface, machine_cidrs)

    host_network_config = {"interfaces": interfaces, "dns-resolver": dns_resolver, "routes": routes}

    mac_interface_map = []
    for i in range(len(primary_macs)):
        mac_interface_map.append({"mac_address": primary_macs[i], "logical_nic_name": f"eth{i}"})
    for i in range(len(secondary_macs)):
        mac_interface_map.append({"mac_address": secondary_macs[i], "logical_nic_name": f"eth{i + len(primary_macs)}"})
    return {"network_yaml": yaml.dump(host_network_config), "mac_interface_map": mac_interface_map}


def _prepare_interfaces(
    machine_cidrs: List[str], provisioning_cidrs: List[str], count: int, *, vlan_enabled: bool, vlan_id: int
) -> List[Dict[str, str]]:
    primary_interface = _prepare_interface(
        _PRIMARY_LOGICAL_INTERFACE, machine_cidrs, count, vlan_enabled=vlan_enabled, vlan_id=vlan_id
    )
    secondary_interface = _prepare_interface(_SECONDARY_LOGICAL_INTERFACE, provisioning_cidrs, count)
    # When VLAN is enabled for primary, return base iface + VLAN iface for primary, plus secondary iface
    if isinstance(primary_interface, list):
        return [*primary_interface, secondary_interface]
    return [primary_interface, secondary_interface]


def _prepare_bonded_interfaces(
    machine_cidrs: List[str],
    provisioning_cidrs: List[str],
    count: int,
    num_bonded_slaves: int,
    bonding_mode: str,
    *,
    vlan_enabled: bool,
    vlan_id: int,
) -> List[Dict[str, Any]]:
    primary_interface = _prepare_bonded_interface("bond0", 0, machine_cidrs, count, num_bonded_slaves, bonding_mode)
    secondary_interface = _prepare_bonded_interface(
        "bond1", num_bonded_slaves, provisioning_cidrs, count, num_bonded_slaves, bonding_mode
    )
    if vlan_enabled:
        vlan_iface = _prepare_vlan_interface(
            parent_logical_iface="bond0", vlan_id=vlan_id, cidrs=machine_cidrs, count=count
        )
        # Return base bond0 (no IP), VLAN bond0.<id> (with IPs), and secondary bond1
        # Ensure bond0 has no IP config when VLAN is used; override by stripping ipv4/ipv6 keys
        primary_interface.pop("ipv4", None)
        primary_interface.pop("ipv6", None)
        primary_interface["ipv4"] = {"enabled": False, "dhcp": False}
        primary_interface["ipv6"] = {"enabled": False, "dhcp": False}
        return [primary_interface, vlan_iface, secondary_interface]
    return [primary_interface, secondary_interface]


def _prepare_interface(
    logical_interface: str, cidrs: List[str], host_count: int, vlan_enabled: bool = False, vlan_id: int = 100
) -> Dict[str, str] | List[Dict[str, str]]:
    # When VLAN is enabled and this is the primary logical interface, create VLAN over the base iface
    if vlan_enabled and logical_interface == _PRIMARY_LOGICAL_INTERFACE:
        base_iface = {
            "name": logical_interface,
            "type": "ethernet",
            "state": "up",
            # Explicitly disable IP on the parent when using VLAN
            "ipv4": {"enabled": False, "dhcp": False},
            "ipv6": {"enabled": False, "dhcp": False},
        }
        vlan_iface = _prepare_vlan_interface(
            parent_logical_iface=logical_interface, vlan_id=vlan_id, cidrs=cidrs, count=host_count
        )
        return [base_iface, vlan_iface]

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


def _prepare_vlan_interface(parent_logical_iface: str, vlan_id: int, cidrs: List[str], count: int) -> Dict[str, Any]:
    """Create an NMState VLAN interface over the given parent with IP settings."""
    ipv4_dict = {}
    ipv6_dict = {}

    ipv6_version, ip_dict = _prepare_ip_dict(cidrs[0], count)

    if not ipv6_version:
        ipv4_dict = ip_dict
    else:
        ipv6_dict = ip_dict

    if not ipv6_version and len(cidrs) > 1:
        _, ipv6_dict = _prepare_ip_dict(cidrs[1], count)

    vlan_iface = {
        "name": f"{parent_logical_iface}.{vlan_id}",
        "type": "vlan",
        "state": "up",
        "vlan": {"base-iface": parent_logical_iface, "id": vlan_id},
    }
    if ipv4_dict:
        vlan_iface["ipv4"] = ipv4_dict
    if ipv6_dict:
        vlan_iface["ipv6"] = ipv6_dict
    return vlan_iface


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
        "port": [f"eth{starting_physical_interface + i}" for i in range(num_bonded_slaves)],
    }


def _prepare_dns_resolver(machine_cidrs: List[str], *, vlan_enabled: bool) -> Dict[str, Dict[str, List[str]]]:
    network = ip_network(machine_cidrs[0])
    dns_ip = str(ip_address(network.network_address) + 1)
    servers = [dns_ip]
    # Only add the host resolv.conf nameservers when VLAN is enabled
    if vlan_enabled:
        try:
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            ns = parts[1]
                            if ns not in servers:
                                servers.append(ns)
        except Exception:
            pass
    return {"config": {"server": servers}}


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
