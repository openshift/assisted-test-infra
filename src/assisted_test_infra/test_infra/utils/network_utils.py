import ipaddress
from typing import List


def get_cidr_by_interface(interface: str) -> str:
    return str(ipaddress.ip_interface(interface).network)


def any_interface_in_cidr(interfaces: List[str], cidr: str) -> bool:
    network = ipaddress.ip_network(cidr)
    return any(ipaddress.ip_interface(ifc).ip in network for ifc in interfaces)


def get_ip_from_interface(interface: str) -> str:
    return str(ipaddress.ip_interface(interface).ip)
