from netaddr import IPAddress

from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.node_controllers.ipip_tunnel import (
    InternalLoopback,
    InternalNetwork,
    LocalServer,
    RemoteServer,
    TunnelExternalEndpoints,
    TunnelInternalEndpoints,
)


class TunnelManager:
    """Singleton tunnel manager , create a tunnel between X86 to  remote node.
    There is a single instance of tunnel, allowing re-using the tunnel created by
    updating routing table dynamically
    """

    _initialized_tunnel = None

    @staticmethod
    def create_tunnel(
        tunnel_source_public: str,
        tunnel_destination_public: str,
        tunnel_internal_source: str,
        tunnel_ext_interface,
        tunnel_local_interface,
    ):
        """
        Singleton object creates a tunnel between X86 to remote machine libvit
        loopback1 (X86) ----- tunnel ------- (Arm64) loopback1
        Internal traffic between loopback1 to remote loopback.
        In order to access to remote libvirt need to update routing on X86

        :param tunnel_source_public:  X86 source public address
        :param tunnel_destination_public:  Remote node external address
        :param tunnel_internal_source: local address as source in the tunnel
        :param tunnel_ext_interface:  tunnel interface - ipp0
        :param tunnel_local_interface: a dummy interface as source in the tunnel
        :return: Instance of tunnel TunnelManager
        """
        if TunnelManager._initialized_tunnel is None:
            TunnelManager._initialized_tunnel = TunnelManager(
                tunnel_source_public,
                tunnel_destination_public,
                tunnel_internal_source,
                tunnel_ext_interface,
                tunnel_local_interface,
            )
        return TunnelManager._initialized_tunnel

    def __init__(
        self,
        tunnel_source_public: str,
        tunnel_destination_public: str,
        tunnel_internal_source: str,
        tunnel_ext_interface,
        tunnel_local_interface,
    ):
        if self._initialized_tunnel:
            raise Exception("Singleton tunnel - allowed to create only once")
        self.tunnel_source_public = tunnel_source_public
        self.tunnel_destination_public = tunnel_destination_public
        source_loopback = InternalLoopback(str(IPAddress(tunnel_internal_source) - 1))
        remote_loopback = InternalLoopback(tunnel_internal_source)

        kwargs_local = {
            "external_endpoints": TunnelExternalEndpoints(
                source_ipv4_tunnel=tunnel_source_public,
                destination_ipv4_tunnel=tunnel_destination_public,
                tunnel_interface=tunnel_ext_interface,
            ),
            "internal_endpoints": TunnelInternalEndpoints(
                source_internal_ipv4=[source_loopback],
                destination_internal_ipv4=[remote_loopback],
                tunnel_interface=tunnel_ext_interface,
                tunnel_local_interface=tunnel_local_interface,
            ),
        }
        kwargs_remote = {
            "external_endpoints": TunnelExternalEndpoints(
                source_ipv4_tunnel=tunnel_destination_public,
                destination_ipv4_tunnel=tunnel_source_public,
                tunnel_interface=tunnel_ext_interface,
            ),
            "internal_endpoints": TunnelInternalEndpoints(
                source_internal_ipv4=[remote_loopback],
                destination_internal_ipv4=[source_loopback],
                tunnel_interface=tunnel_ext_interface,
                tunnel_local_interface=tunnel_local_interface,
            ),
        }
        self.local_server = LocalServer(shell_callback=utils.subprocess_run, **kwargs_local)
        self.remote_server = RemoteServer(shell_callback=utils.run_command, **kwargs_remote)
        self.local_server.initialize_tunnel()
        self.remote_server.initialize_tunnel()
        self._initialized_tunnel = self

    def update_tunnel_network(self, action, source_internal, destination_internal):
        """Modify existing tunnel routing to allow access to libvirt networks
        From X86 we will have to route the traffic into the tunnel to remote node
        Updating local node iptables to prevent nat between source to remote nodes (internally)
        Updating no nat between remote server libvirt to X86
        :param action:  add or delete
        :param source_internal:
        :param destination_internal
        :return: None
        """
        destination_internal = [InternalNetwork(net) for net in destination_internal]
        source_internal = [InternalNetwork(net) for net in source_internal]
        self.local_server.update_tunnel_routing(destination_internal, action)
        self.local_server.iptables_no_nat_networks(source_internal, destination_internal, action)
        # no nat on remote server from libvirt ranges to loopback
        self.remote_server.iptables_no_nat_networks(destination_internal, source_internal, action)

    def clean_tunnels(self):
        self.local_server.cleanup()
        self.remote_server.cleanup()
