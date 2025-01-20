import re
import socket
from typing import List

import waiting

import consts
from assisted_test_infra.test_infra.tools import TerraformUtils
from service_client import log


class LoadBalancerController:
    def __init__(self, tf: TerraformUtils):
        self._tf = tf

    def set_load_balancing_config(self, load_balancer_ip: str, master_ips: List[str], worker_ips: List[str]) -> None:
        load_balancer_config_file = self._render_load_balancer_config_file(load_balancer_ip, master_ips, worker_ips)
        self._tf.change_variables(
            {"load_balancer_ip": load_balancer_ip, "load_balancer_config_file": load_balancer_config_file}
        )
        print("test")
        self._wait_for_load_balancer(load_balancer_ip)

    @staticmethod
    def _render_socket_endpoint(ip: str, port: int) -> str:
        return f"{ip}:{port}" if "." in ip else f"[{ip}]:{port}"

    def _render_upstream_server(self, ip: str, port: int) -> str:
        return f"\t\tserver {self._render_socket_endpoint(ip, port)};"

    def _render_upstream_servers(self, master_ips: List[str], port: int) -> str:
        return "\n".join([self._render_upstream_server(ip, port) for ip in master_ips]) + "\n"

    def _render_upstream_block(self, master_ips: List[str], port: int, upstream_name: str) -> str:
        return f"\tupstream {upstream_name} {{\n{self._render_upstream_servers(master_ips, port)}\t}}\n"

    def _render_server_block(self, load_balancer_ip: str, port: int, upstream_name: str) -> str:
        return (
            f"\tserver {{\n\t\tlisten {self._render_socket_endpoint(load_balancer_ip, port)};"
            f"\n\t\tproxy_pass {upstream_name};\n\t}}\n"
        )

    def _render_port_entities(self, load_balancer_ip: str, master_ips: List[str], port: int) -> str:
        upstream_name = f'upstream_{re.sub(r"[.:]", r"_", load_balancer_ip)}_{port}'
        return self._render_upstream_block(master_ips, port, upstream_name) + self._render_server_block(
            load_balancer_ip, port, upstream_name
        )

    def _render_load_balancer_config_file(
        self, load_balancer_ip: str, master_ips: List[str], worker_ips: List[str]
    ) -> str:
        api_stream = [
            self._render_port_entities(load_balancer_ip, master_ips, port)
            for port in [consts.DEFAULT_LOAD_BALANCER_PORT, 22623]
        ]
        route_stream = [
            self._render_port_entities(load_balancer_ip, worker_ips if worker_ips else master_ips, port)
            for port in [80, 443]
        ]
        return "\n".join(api_stream + route_stream)

    def _connect_to_load_balancer(self, load_balancer_ip: str) -> bool:
        family = socket.AF_INET6 if ":" in load_balancer_ip else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.connect((load_balancer_ip, consts.DEFAULT_LOAD_BALANCER_PORT))
                log.info(
                    f"Successfully connected to load balancer "
                    f"{load_balancer_ip}:{consts.DEFAULT_LOAD_BALANCER_PORT}"
                )
                return True
        except Exception as e:
            log.warning(
                "Could not connect to load balancer endpoint %s: %s",
                self._render_socket_endpoint(load_balancer_ip, consts.DEFAULT_LOAD_BALANCER_PORT),
                e,
            )
            return False

    def _wait_for_load_balancer(self, load_balancer_ip: str) -> None:
        log.info("Waiting for load balancer %s to be up", load_balancer_ip)
        waiting.wait(
            lambda: self._connect_to_load_balancer(load_balancer_ip),
            timeout_seconds=120,
            sleep_seconds=5,
            waiting_for="Waiting for load balancer to be active",
        )
