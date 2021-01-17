import os
import shutil
import socket
import logging
from jinja2 import Environment, PackageLoader

from test_infra import utils

PROXY_USER = 'assisted'
PROXY_USER_PASS = 'redhat'


class ProxyController:
    def __init__(self, name=None, port=None, denied_port=None, authenticated=False, dir=None):
        if not name:
            self.address = ''
        else:
            self.name = name
            self.port = port
            self.authenticated = authenticated
            self.image = 'quay.io/sameersbn/squid'
            self.dir = dir
            self._set_server_address()
            self._create_conf_from_template(denied_port=denied_port)
            self._create_user_file_for_auth()
            self._run_proxy_server()

    def remove(self):
        if self.address:
            logging.info(f'Removing Proxy Server {self.name}')
            utils.remove_running_container(container_name=self.dir)
            self._remove_config()

    def _set_server_address(self):
        host_name = socket.gethostname()
        host_ip = socket.gethostbyname(host_name)
        proxy_user_path = f'{PROXY_USER}:{PROXY_USER_PASS}@' if self.authenticated else ''
        self.address = f'http://{proxy_user_path}{host_ip}:{self.port}'

    def _run_proxy_server(self):
        logging.info(f'Running Proxy Server {self.name}')
        run_flags = ['-d', '--restart=always', '--network=host',f'--volume {self.config_dir_path}:/etc/squid/', f'--publish {self.port}:{self.port}']
        utils.run_container(container_name=self.dir, image=self.image, flags=run_flags)

    def _create_conf_from_template(self, denied_port):
        logging.info(f'Creating Config for Proxy Server {self.name}')
        os.mkdir(f'/tmp/{self.dir}')
        self.config_dir_path = f'/tmp/{self.dir}/{self.name}'
        os.mkdir(self.config_dir_path)

        env = Environment(loader=PackageLoader('test_infra.controllers.proxy_controller', 'templates'))
        template = env.get_template('squid.conf.j2')
        config = template.render(port=self.port, denied_port=denied_port, authenticated=self.authenticated)

        with open(f"{self.config_dir_path}/squid.conf", 'x') as f:
            f.writelines(config)

    def _remove_config(self):
        logging.info(f'Removing Config for Proxy Server {self.dir}/{self.name}')
        if os.path.exists(f'/tmp/{self.dir}'):
            path = os.path.abspath(f'/tmp/{self.dir}')
            shutil.rmtree(path)

    def _create_user_file_for_auth(self):
        if self.authenticated:
            create_user_file_cmd = f'htpasswd -b -c {self.config_dir_path}/squid-users {PROXY_USER} {PROXY_USER_PASS}'
            utils.run_command(create_user_file_cmd, shell=True)

            self.user_file_path = f'{self.config_dir_path}/squid-users'
