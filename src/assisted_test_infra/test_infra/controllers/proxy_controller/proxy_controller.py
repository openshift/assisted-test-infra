import os
import shutil
import socket

from jinja2 import Environment, PackageLoader

import consts
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.containerized_controller import ContainerizedController
from service_client import log


class ProxyController(ContainerizedController):
    PROXY_USER = "assisted"
    PROXY_USER_PASS = "redhat"
    IMAGE = "quay.io/sameersbn/squid"

    def __init__(
        self,
        name=None,
        port=consts.DEFAULT_PROXY_SERVER_PORT,
        denied_port=None,
        authenticated=False,
        host_ip=None,
        is_ipv6=False,
    ):
        super().__init__(name, port, self.IMAGE)

        if not name:
            self.address = ""
        else:
            self.authenticated = authenticated
            self._is_ipv6 = is_ipv6
            self._set_server_address(host_ip)
            self._create_conf_from_template(denied_port=denied_port)
            self._create_user_file_for_auth()
            self._extra_flags = [f"--volume {self.config_dir_path}:/etc/squid/"]

    def _on_container_removed(self):
        self._remove_config()

    def _set_server_address(self, host_ip):
        host_name = socket.gethostname()
        host_ip = host_ip or socket.gethostbyname(host_name)
        proxy_user_path = f"{self.PROXY_USER}:{self.PROXY_USER_PASS}@" if self.authenticated else ""
        address = f"{proxy_user_path}{host_ip}"
        self.address = f"http://{f'[{address}]' if self._is_ipv6 else address}:{self._port}"
        log.info(f"Proxy server address {self.address}")

    def _create_conf_from_template(self, denied_port):
        log.info(f"Creating Config for Proxy Server {self._name}")
        shutil.rmtree(f"/tmp/{self._name}", ignore_errors=True)
        os.mkdir(f"/tmp/{self._name}")
        self.config_dir_path = f"/tmp/{self._name}/{self._name}"
        os.mkdir(self.config_dir_path)

        env = Environment(
            loader=PackageLoader("assisted_test_infra.test_infra.controllers.proxy_controller", "templates")
        )
        template = env.get_template("squid.conf.j2")
        config = template.render(port=self._port, denied_port=denied_port, authenticated=self.authenticated)

        with open(f"{self.config_dir_path}/squid.conf", "x") as f:
            f.writelines(config)

    def _remove_config(self):
        log.info(f"Removing Config for Proxy Server {self._name}/{self._name}")
        if os.path.exists(f"/tmp/{self._name}"):
            path = os.path.abspath(f"/tmp/{self._name}")
            shutil.rmtree(path)

    def _create_user_file_for_auth(self):
        if self.authenticated:
            create_user_file_cmd = (
                f"htpasswd -b -c {self.config_dir_path}/squid-users {self.PROXY_USER} {self.PROXY_USER_PASS}"
            )
            utils.run_command(create_user_file_cmd, shell=True)
            self.user_file_path = f"{self.config_dir_path}/squid-users"

    def run(self, **kwargs):
        if self._name:
            super().run(**kwargs)
