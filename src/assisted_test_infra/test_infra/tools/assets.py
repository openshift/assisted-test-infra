import json
import os
from typing import Any, Dict, List, Optional, Union

import libvirt
import netifaces
from munch import Munch
from netaddr import IPAddress, IPNetwork, IPRange
from netaddr.core import AddrFormatError

import consts
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from consts.consts import DEFAULT_LIBVIRT_URI
from service_client import log
from tests.global_variables import DefaultVariables

global_variables = DefaultVariables()

class LibvirtNetworkAssets:
    """An assets class that stores values based on the current available
    resources, in order to allow multiple installations while avoiding
    conflicts."""

    ASSETS_LOCKFILE_DEFAULT_PATH = "/tmp"
    BASE_ASSET = {
        "machine_cidr": global_variables.machine_cidr_ipv4,
        "machine_cidr6": global_variables.machine_cidr_ipv6,
        "provisioning_cidr": consts.BaseAsset.PROVISIONING_CIDR,
        "provisioning_cidr6": consts.BaseAsset.PROVISIONING_CIDR6,
        "libvirt_network_if": consts.BaseAsset.NETWORK_IF,
        "libvirt_secondary_network_if": consts.BaseAsset.SECONDARY_NETWORK_IF,
    }

    def __init__(
        self,
        assets_file: str = consts.TF_NETWORK_POOL_PATH,
        lock_file: Optional[str] = None,
        base_asset: dict[str, Any] = BASE_ASSET,
        libvirt_uri: str = global_variables.libvirt_uri,
    ):
        self._assets_file = assets_file
        self._lock_file = lock_file or os.path.join(
            self.ASSETS_LOCKFILE_DEFAULT_PATH, os.path.basename(assets_file) + ".lock"
        )

        self._allocated_ips_objects = []
        self._allocated_bridges = []
        self._taken_assets = set([])
        self._asset = base_asset.copy()
        self._default_variables = DefaultVariables()
        self._libvirt_uri = libvirt_uri

    def get(self) -> Munch:
        self._verify_asset_fields()

        with utils.file_lock_context(self._lock_file):
            assets_in_use = self._get_assets_in_use_from_assets_file()

            self._fill_allocated_ips_and_bridges_from_assets_file(assets_in_use)
            self._fill_allocated_ips_and_bridges_by_interface()
            self._fill_virsh_allocated_ips_and_bridges()

            self._override_ip_networks_values_if_not_free()
            self._override_network_bridges_values_if_not_free()

            self._taken_assets.add(str(self._asset))
            assets_in_use.append(self._asset)

            self._dump_all_assets_in_use_to_assets_file(assets_in_use)

        self._allocated_bridges.clear()
        self._allocated_ips_objects.clear()

        log.info("Taken asset: %s", self._asset)
        return Munch.fromDict(self._asset)

    def _verify_asset_fields(self):
        for field in consts.REQUIRED_ASSET_FIELDS:
            assert field in self._asset, f"missing field {field} in asset {self._asset}"

    def _fill_allocated_ips_and_bridges_by_interface(self):
        if self._libvirt_uri != DEFAULT_LIBVIRT_URI:
            # it means we are not trying to compute networks for the local machine
            # skip this step
            return

        for interface in netifaces.interfaces():
            self._add_allocated_net_bridge(interface)
            try:
                ifaddresses = netifaces.ifaddresses(interface)
            except ValueError:
                log.debug(f"Interface {interface} no longer exists. It might has been removed intermediately")
                continue

            for ifaddress in ifaddresses.values():
                for item in ifaddress:
                    try:
                        self._add_allocated_ip(IPAddress(item["addr"]))
                    except AddrFormatError:
                        continue

    def _fill_allocated_ips_and_bridges_from_assets_file(self, assets_in_use: List[Dict]):
        for asset in assets_in_use:
            self._verify_asset_fields()

            for ip_network_field in consts.IP_NETWORK_ASSET_FIELDS:
                self._add_allocated_ip(IPNetwork(asset[ip_network_field]))

            self._add_allocated_net_bridge(asset["libvirt_network_if"])
            self._add_allocated_net_bridge(asset["libvirt_secondary_network_if"])

    def _fill_virsh_allocated_ips_and_bridges(self):
        with LibvirtController.connection_context(libvirt_uri=self._libvirt_uri) as conn:
            for net in conn.listAllNetworks():
                # In parallel tests net object may be deleted by tests cleanup
                try:
                    for lease in net.DHCPLeases():
                        net_bridge = lease.get("iface")
                        if net_bridge:
                            self._add_allocated_net_bridge(net_bridge)

                        ipaddr = lease.get("ipaddr")
                        if ipaddr:
                            self._add_allocated_ip(IPAddress(ipaddr))
                except libvirt.libvirtError:
                    log.info(f"Can not get dhcp leases from {net.name()}")

    def _override_ip_networks_values_if_not_free(self):
        log.info("IPs in use: %s", self._allocated_ips_objects)

        for ip_network_field in consts.IP_NETWORK_ASSET_FIELDS:
            ip_network = IPNetwork(self._asset[ip_network_field])
            self._set_next_available_ip_network(ip_network)
            self._add_allocated_ip(ip_network)
            self._asset[ip_network_field] = str(ip_network)

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
        five_hextets_ips_range = 2**72
        ip_network += five_hextets_ips_range

    def _add_allocated_ip(self, ip: Union[IPNetwork, IPRange, IPAddress]):
        self._allocated_ips_objects.append(ip)

    def _override_network_bridges_values_if_not_free(self):
        log.info("Bridges in use: %s", self._allocated_bridges)

        if self._is_net_bridge_allocated(self._asset["libvirt_network_if"]):
            self._asset["libvirt_network_if"] = self._get_next_available_net_bridge()
            self._add_allocated_net_bridge(self._asset["libvirt_network_if"])

        if self._is_net_bridge_allocated(self._asset["libvirt_secondary_network_if"]):
            net_bridge = self._get_next_available_net_bridge(prefix="stt")
            self._asset["libvirt_secondary_network_if"] = net_bridge

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
        log.info("Returning %d assets", len(self._taken_assets))
        log.debug("Assets to return: %s", self._taken_assets)

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
