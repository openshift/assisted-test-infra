import json
from typing import List

from assisted_service_client import Host, Interface, Inventory

DEFAULT_HOSTNAME = "localhost"


class ClusterHost:
    def __init__(self, host_model: Host):
        self.__host_model = host_model
        self.__inventory = Inventory(**json.loads(self.__host_model.inventory))

    def get_id(self):
        return self.__host_model.id

    def get_inventory(self) -> Inventory:
        return self.__inventory

    def get_hostname(self) -> str:
        return (
            self.__host_model.requested_hostname if self.__host_model.requested_hostname else self.__inventory.hostname
        )

    def interfaces(self) -> List[Interface]:
        return [Interface(**interface) for interface in self.__inventory.interfaces]

    def macs(self) -> List[str]:
        return [ifc.mac_address.lower() for ifc in self.interfaces()]

    def ips(self) -> List[str]:
        return self.ipv4_addresses() + self.ipv6_addresses()

    def ipv4_addresses(self) -> List[str]:
        results = list()

        for ifc in self.interfaces():
            results.extend(ifc.ipv4_addresses)

        return results

    def ipv6_addresses(self) -> List[str]:
        results = list()

        for ifc in self.interfaces():
            results.extend(ifc.ipv6_addresses)

        return results
