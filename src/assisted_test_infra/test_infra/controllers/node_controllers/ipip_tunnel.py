from typing import Callable

from service_client import log


class TunnelExternalEndpoints:
    """External tunnel public addresses (public IP)
    Create the external endpoints and the interface name
    """

    def __init__(
        self, source_ipv4_tunnel: str, destination_ipv4_tunnel: str, tunnel_interface: str, tunnel_type: str = "ipip"
    ):
        self.source_ipv4_tunnel = source_ipv4_tunnel
        self.destination_ipv4_tunnel = destination_ipv4_tunnel
        self.tunnel_interface = tunnel_interface
        self.tunnel_type = tunnel_type


class InternalAddress:
    network_source_type = None

    def __init__(self, internal_ipv4):
        self.internal_ipv4 = internal_ipv4


class InternalLoopback(InternalAddress):
    network_source_type = "loopback"


class InternalNetwork(InternalLoopback):
    network_source_type = "network"


class TunnelInternalEndpoints:
    """Internal tunnel (Inner Ip) inside traffic between nodes
    The internal traffic is the private addresses that routable
    Each Node has:
    - source_internal which is a loopback interface
    - destination_internal which is the remote private networks route to
    - bind to tunnel_interface for routing

    Each node must have a source internal loopback for internal traffic
    Each node route traffic to remote internal network via the  tunnel_interface
    """

    def __init__(
        self,
        source_internal_ipv4: list[InternalAddress],
        destination_internal_ipv4: list[str],
        tunnel_interface: str,
        tunnel_local_interface: str,
    ):
        self.source_internal_ipv4 = source_internal_ipv4
        self.destination_internal_ipv4 = destination_internal_ipv4
        self.tunnel_interface = tunnel_interface
        self.tunnel_local_interface = tunnel_local_interface


class Ipv4InIpv4Tunnel:
    def __init__(
        self,
        shell_callback: Callable,
        external_endpoints: TunnelExternalEndpoints,
        internal_endpoints: TunnelInternalEndpoints,
    ):
        """Initialize shell callback to use local or remote
        :param shell_callback:
        """
        self.shell_callback = shell_callback
        self.external_endpoints = external_endpoints
        self.internal_endpoints = internal_endpoints

    def link_exists(self):
        cmd = f"ip link show {self.external_endpoints.tunnel_interface}"
        try:
            _, _, status = self.shell_callback(cmd, shell=True)
            if status == 0:
                return True
        except RuntimeError:
            return False
        return False

    def tunnel_action(self, action="add"):
        tunnel = (
            f"ip link {action} name {self.external_endpoints.tunnel_interface} type"
            f" {self.external_endpoints.tunnel_type}"
            f" local {self.external_endpoints.source_ipv4_tunnel}"
            f" remote {self.external_endpoints.destination_ipv4_tunnel}"
        )
        log.info(f"tunnel_action: {tunnel}")
        self.shell_callback(tunnel, shell=True)

    def tunnel_state(self, action="up"):
        activate = f"ip link set {self.external_endpoints.tunnel_interface} {action}"
        log.info(f"tunnel_state: {activate}")
        self.shell_callback(activate, shell=True)

    def tunnel_source_address_internal(self, action="add"):
        # Add address to loopback interface as source
        for internal_ipv4 in self.internal_endpoints.source_internal_ipv4:
            if internal_ipv4.network_source_type == "loopback":
                create_interface = f"ip link {action} name {self.internal_endpoints.tunnel_local_interface} type dummy"
                add_address = (
                    f"ip addr {action} {internal_ipv4.internal_ipv4}"
                    f" dev {self.internal_endpoints.tunnel_local_interface}"
                )
                log.info(f"create_interface {create_interface}")
                self.shell_callback(create_interface, shell=True)
                if action == "add":
                    log.info(f"add_address  {add_address}")
                    self.shell_callback(add_address, shell=True)
                # Bind the source loopback to the tunnel iterface as a source address
                source_internal = (
                    f"ip addr {action} {internal_ipv4.internal_ipv4}" f" dev {self.internal_endpoints.tunnel_interface}"
                )
                self.shell_callback(source_internal, shell=True)

    def _tunnel_destination_route_internal(self, action="add"):
        for destination in self.internal_endpoints.destination_internal_ipv4:
            destination_internal = (
                f"ip route {action} {destination.internal_ipv4}" f" dev {self.internal_endpoints.tunnel_interface}"
            )
            log.info(f"tunnel_destination_route_internal {destination_internal}")
            self.shell_callback(destination_internal, shell=True)

    def _iptables_no_nat(self, action="I"):
        index_table = 1 if action == "I" else ""
        for source in self.internal_endpoints.source_internal_ipv4:
            for destination in self.internal_endpoints.destination_internal_ipv4:
                no_nat = (
                    f"iptables -t nat -{action} POSTROUTING {index_table}"
                    f" -s {source.internal_ipv4}"
                    f" -d {destination.internal_ipv4} -j RETURN"
                )
                self.shell_callback(no_nat, shell=True)
                index_table += 1 if action == "I" else ""

    def update_tunnel_routing(self, destination_internal_ipv4, action="add"):
        for destination in destination_internal_ipv4:
            destination_internal = (
                f"ip route {action} {destination.internal_ipv4}" f" dev {self.internal_endpoints.tunnel_interface}"
            )
            log.info(f"tunnel_destination_route_internal {destination_internal}")
            self.shell_callback(destination_internal, shell=True)

    def iptables_no_nat_networks(self, source_internal_ipv4, destination_internal_ipv4, action="I"):
        index_table = 1 if action == "I" else ""
        for source in source_internal_ipv4:
            for destination in destination_internal_ipv4:
                no_nat = (
                    f"iptables -t nat -{action} POSTROUTING {index_table}"
                    f" -s {source.internal_ipv4}"
                    f" -d {destination.internal_ipv4} -j RETURN"
                )
                self.shell_callback(no_nat, shell=True)
                index_table += 1 if action == "I" else ""

    def initialize_tunnel(self):
        self.tunnel_action()
        self.tunnel_state()
        self.tunnel_source_address_internal()
        self._tunnel_destination_route_internal()
        self._iptables_no_nat()

    def cleanup(self):
        self.tunnel_source_address_internal(action="del")
        self.tunnel_action(action="del")
        self.iptables_no_nat(action="D")


class LocalServer(Ipv4InIpv4Tunnel):
    pass


class RemoteServer(Ipv4InIpv4Tunnel):
    pass
