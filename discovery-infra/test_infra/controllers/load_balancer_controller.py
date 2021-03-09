import re
import waiting
import socket
from logger import log


class LoadBalancerController:

    def __init__(self, tf):
        self._tf = tf

    def _render_socket_endpoint(self, ip, port):
        return f'{ip}:{port}' if '.' in ip else f'[{ip}]:{port}'

    def _render_upstream_server(self, ip, port):
        return f'\t\tserver {self._render_socket_endpoint(ip, port)};'

    def _render_upstream_servers(self, master_ips, port):
        return '\n'.join([self._render_upstream_server(ip, port) for ip in master_ips]) + '\n'

    def _render_upstream_block(self, master_ips, port, upstream_name):
        return f'\tupstream {upstream_name} {{\n{self._render_upstream_servers(master_ips, port)}\t}}\n'

    def _render_server_block(self, load_balancer_ip, port, upstream_name):
        return f'\tserver {{\n\t\tlisten {self._render_socket_endpoint(load_balancer_ip, port)};\n\t\tproxy_pass {upstream_name};\n\t}}\n'

    def _render_port_entities(self, load_balancer_ip, master_ips, port):
        upstream_name = f'upstream_{re.sub(r"[.:]", r"_", load_balancer_ip)}_{port}'
        return self._render_upstream_block(master_ips, port, upstream_name) + self._render_server_block(load_balancer_ip, port, upstream_name)

    def _render_load_balancer_config_file(self, load_balancer_ip, master_ips, worker_ips):
        return '\n'.join([self._render_port_entities(load_balancer_ip, master_ips, port) for port in [6443, 22623]]) + '\n' + \
            '\n'.join([self._render_port_entities(load_balancer_ip, worker_ips, port) for port in [80, 443]])

    def _connect_to_load_balancer(self, load_balancer_ip):
        family = socket.AF_INET6 if ':' in load_balancer_ip else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.connect((load_balancer_ip, 6443))
                return True
        except Exception as e:
            log.warning("Could not connect to load balancer endpoint %s: %s", self._render_socket_endpoint(load_balancer_ip, 6443), e)
            return False

    def _wait_for_load_balancer(self, load_balancer_ip):
        log.info("Waiting for load balancer %s to be up", load_balancer_ip)
        waiting.wait(lambda : self._connect_to_load_balancer(load_balancer_ip), timeout_seconds=120, sleep_seconds=5, waiting_for="Waiting for load balancer to be active")

    def set_load_balancing_config(self, load_balancer_ip, master_ips, worker_ips):
        load_balancer_config_file = self._render_load_balancer_config_file(load_balancer_ip, master_ips, worker_ips)
        self._tf.change_variables({"load_balancer_ip": load_balancer_ip, "load_balancer_config_file": load_balancer_config_file})
        self._wait_for_load_balancer(load_balancer_ip)