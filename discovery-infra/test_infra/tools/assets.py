import json
import logging
import os

import netifaces

from typing import Optional, List, Dict, Union

from munch import Munch
from netaddr import IPNetwork, IPRange, IPAddress
from netaddr.core import AddrFormatError

from test_infra import consts, utils
from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController


class LibvirtNetworkAssets:
    """ An assets class that stores values based on the current available
        resources, in order to allow multiple installations while avoiding
        conflicts. """

    ASSETS_LOCKFILE_DEFAULT_PATH = "/tmp"
    BASE_ASSET = {
        "machine_cidr": consts.BaseAsset.MACHINE_CIDR,
        "machine_cidr6": consts.BaseAsset.MACHINE_CIDR6,
        "provisioning_cidr": consts.BaseAsset.PROVISIONING_CIDR,
        "provisioning_cidr6": consts.BaseAsset.PROVISIONING_CIDR6,
        "libvirt_network_if": consts.BaseAsset.NETWORK_IF,
        "libvirt_secondary_network_if": consts.BaseAsset.SECONDARY_NETWORK_IF,
    }

    def __init__(
            self,
            assets_file: str = consts.TF_NETWORK_POOL_PATH,
            lock_file: Optional[str] = None,
    ):
        self._assets_file = assets_file
        self._lock_file = lock_file or os.path.join(
            self.ASSETS_LOCKFILE_DEFAULT_PATH,
            os.path.basename(assets_file) + ".lock"
        )

        self._allocated_ips_objects = []
        self._allocated_bridges = []
        self._taken_assets = set([])

    def get(self) -> Munch:
        asset = self.BASE_ASSET.copy()
        self._verify_asset_fields(asset)

        with utils.file_lock_context(self._lock_file):
            assets_in_use = self._get_assets_in_use_from_assets_file()

            self._fill_allocated_ips_and_bridges_from_assets_file(assets_in_use)
            self._fill_allocated_ips_and_bridges_by_interface()
            self._fill_virsh_allocated_ips_and_bridges()

            self._override_ip_networks_values_if_not_free(asset)
            self._override_network_bridges_values_if_not_free(asset)

            self._taken_assets.add(str(asset))
            assets_in_use.append(asset)

            self._dump_all_assets_in_use_to_assets_file(assets_in_use)

        self._allocated_bridges.clear()
        self._allocated_ips_objects.clear()

        logging.info("Taken asset: %s", asset)
        return Munch.fromDict(asset)

    @staticmethod
    def _verify_asset_fields(asset: Dict):
        for field in consts.REQUIRED_ASSET_FIELDS:
            assert field in asset, f"missing field {field} in asset {asset}"

    def _fill_allocated_ips_and_bridges_by_interface(self):
        for interface in netifaces.interfaces():
            self._add_allocated_net_bridge(interface)
            for ifaddresses in netifaces.ifaddresses(interface).values():
                for item in ifaddresses:
                    try:
                        self._add_allocated_ip(IPAddress(item['addr']))
                    except AddrFormatError:
                        continue

    def _fill_allocated_ips_and_bridges_from_assets_file(self, assets_in_use: List[Dict]):
        for asset in assets_in_use:
            self._verify_asset_fields(asset)

            for ip_network_field in consts.IP_NETWORK_ASSET_FIELDS:
                self._add_allocated_ip(IPNetwork(asset[ip_network_field]))

            self._add_allocated_net_bridge(asset["libvirt_network_if"])
            self._add_allocated_net_bridge(asset["libvirt_secondary_network_if"])

    def _fill_virsh_allocated_ips_and_bridges(self):
        with LibvirtController.connection_context() as conn:
            for net in conn.listAllNetworks():
                for lease in net.DHCPLeases():
                    net_bridge = lease.get('iface')
                    if net_bridge:
                        self._add_allocated_net_bridge(net_bridge)

                    ipaddr = lease.get('ipaddr')
                    if ipaddr:
                        self._add_allocated_ip(IPAddress(ipaddr))

    def _override_ip_networks_values_if_not_free(self, asset: Dict):
        logging.info("IPs in use: %s", self._allocated_ips_objects)

        for ip_network_field in consts.IP_NETWORK_ASSET_FIELDS:
            ip_network = IPNetwork(asset[ip_network_field])
            self._set_next_available_ip_network(ip_network)
            self._add_allocated_ip(ip_network)
            asset[ip_network_field] = str(ip_network)

    def _set_next_available_ip_network(self, ip_network: IPNetwork):
        while self._is_ip_network_allocated(ip_network):
            if ip_network.version == 6:  # IPv6
                self._increment_ipv6_network_grp(ip_network)
            else:
                ip_network += 1

    def _is_ip_network_allocated(self, ip_network: IPNetwork) -> bool:
        for ip_addr in self._allocated_ips_objects:
            if ip_addr in ip_network:
                return True

        return False

    @staticmethod
    def _increment_ipv6_network_grp(ip_network: IPNetwork):
        # IPNetwork contains an IPAddress object which represents the global
        # routing prefix (GRP), the subnet id and the host address.
        # To increment the IPNetwork while keeping its validity we should update
        # only the GRP section, which is the first 3 hextets of the IPAddress.
        # The third hextet starts at the 72th bit of the IPAddress, means that
        # there are 2^72 possibilities within the other 5 hextets. This number
        # is needed to be added to the IPAddress to effect the GRP section.
        five_hextets_ips_range = 2 ** 72
        ip_network += five_hextets_ips_range

    def _add_allocated_ip(self, ip: Union[IPNetwork, IPRange, IPAddress]):
        self._allocated_ips_objects.append(ip)

    def _override_network_bridges_values_if_not_free(self, asset: Dict):
        logging.info("Bridges in use: %s", self._allocated_bridges)

        if self._is_net_bridge_allocated(asset["libvirt_network_if"]):
            asset["libvirt_network_if"] = self._get_next_available_net_bridge()
            self._add_allocated_net_bridge(asset["libvirt_network_if"])

        if self._is_net_bridge_allocated(asset["libvirt_secondary_network_if"]):
            net_bridge = self._get_next_available_net_bridge(prefix="stt")
            asset["libvirt_secondary_network_if"] = net_bridge

    def _get_next_available_net_bridge(self, prefix: str = "tt") -> str:
        index = 0
        while self._is_net_bridge_allocated(f"{prefix}{index}"):
            index += 1

        return f"{prefix}{index}"

    def _is_net_bridge_allocated(self, net_bridge: str) -> bool:
        return net_bridge in self._allocated_bridges

    def _add_allocated_net_bridge(self, net_bridge: str):
        self._allocated_bridges.append(net_bridge)

    def release_all(self):
        with utils.file_lock_context(self._lock_file):
            assets_in_use = self._get_assets_in_use_from_assets_file()
            self._remove_taken_assets_from_all_assets_in_use(assets_in_use)
            self._dump_all_assets_in_use_to_assets_file(assets_in_use)

    def _get_assets_in_use_from_assets_file(self) -> List[Dict]:
        if not os.path.isfile(self._assets_file):
            return []

        with open(self._assets_file) as fp:
            return json.load(fp)

    def _remove_taken_assets_from_all_assets_in_use(self, assets_in_use: List[Dict]):
        logging.info("Returning %d assets", len(self._taken_assets))
        logging.debug("Assets to return: %s", self._taken_assets)

        indexes_to_pop = []
        for i in range(len(assets_in_use)):
            if str(assets_in_use[i]) in self._taken_assets:
                indexes_to_pop.append(i)

        while indexes_to_pop:
            assets_in_use.pop(indexes_to_pop.pop())

        self._taken_assets.clear()

    def _dump_all_assets_in_use_to_assets_file(self, assets_in_use: List[Dict]):
        with open(self._assets_file, "w") as fp:
            json.dump(assets_in_use, fp)
