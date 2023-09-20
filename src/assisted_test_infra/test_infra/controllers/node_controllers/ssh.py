import logging
import socket
import time
from ipaddress import IPv4Address, ip_address
from pathlib import Path
from typing import Optional

import paramiko
import scp

from service_client import log

logging.getLogger("paramiko").setLevel(logging.CRITICAL)


class SshConnection:
    def __init__(self, ip, private_ssh_key_path: Optional[Path] = None, username="core", port=22, **kwargs):
        self._ip = ip
        self._username = username
        self._key_path = private_ssh_key_path
        self._port = port
        self._ssh_client = None

    @property
    def ssh_client(self):
        return self._ssh_client

    @ssh_client.setter
    def ssh_client(self, connection):
        self._ssh_client = connection

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def connect(self, timeout=60):
        log.info("Going to connect to ip %s", self._ip)
        self.wait_for_tcp_server()
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.known_hosts = None
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._ssh_client.connect(
            hostname=self._ip,
            port=self._port,
            username=self._username,
            allow_agent=False,
            timeout=timeout,
            look_for_keys=False,
            auth_timeout=timeout,
            pkey=paramiko.RSAKey.from_private_key_file(self._key_path),
        )
        self._ssh_client.get_transport().set_keepalive(15)

    def wait_for_tcp_server(self, timeout=60, interval=0.1):
        log.info("Wait for %s to be available", self._ip)
        before = time.time()
        while time.time() - before < timeout:
            if self._raw_tcp_connect((self._ip, self._port)):
                return
            time.sleep(interval)
        raise TimeoutError(
            "SSH TCP Server '[%(hostname)s]:%(port)s' did not respond within timeout"
            % dict(hostname=self._ip, port=self._port)
        )

    @classmethod
    def _raw_tcp_connect(cls, tcp_endpoint):
        if isinstance(ip_address(tcp_endpoint[0]), IPv4Address):
            family = socket.AF_INET
        else:
            family = socket.AF_INET6

        s = socket.socket(family=family)
        try:
            s.connect(tcp_endpoint)
            return True
        except BaseException:
            return False
        finally:
            s.close()

    def script(self, bash_script, verbose=True, timeout=60):
        try:
            logging.info("Executing %s on %s", bash_script, self._ip)
            return self.execute(bash_script, timeout, verbose)
        except RuntimeError as e:
            e.args += (f'When running bash script "{bash_script}"',)
            raise

    def execute(self, command, timeout=60, verbose=True):
        if not self._ssh_client:
            self.connect()
        if verbose:
            name = getattr(self._ssh_client, "name", "")
            logging.info(f"{self._ip} execute: {command} {'on ' + name if name else name}")
        stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=timeout)
        status = stdout.channel.recv_exit_status()
        output = stdout.readlines()
        output = "".join(output)
        if verbose and output:
            log.debug(f"SSH Execution output: \n{output}")
        if status != 0:
            e = RuntimeError(
                f"Failed executing, status '{status}', output was:\n{output} stderr \n{stderr.readlines()}"
            )
            e.output = output
            raise e
        return output

    def upload_file(self, local_source_path, remote_target_path):
        with scp.SCPClient(self._ssh_client.get_transport()) as scp_client:
            logging.info(f"{self._ip} upload_file: {local_source_path} to {remote_target_path}")
            scp_client.put(local_source_path, remote_target_path)

    def download_file(self, remote_source_path, local_target_path):
        with scp.SCPClient(self._ssh_client.get_transport()) as scp_client:
            logging.info(f"{self._ip} download_file: {remote_source_path} to {local_target_path}")
            scp_client.get(remote_source_path, local_target_path)

    def background_script(self, bash_script, connect_timeout=10 * 60):
        command = "\n".join(
            [
                "nohup sh << 'RACKATTACK_SSH_RUN_SCRIPT_EOF' >& /dev/null &",
                bash_script,
                "RACKATTACK_SSH_RUN_SCRIPT_EOF\n",
            ]
        )
        transport = self._ssh_client.get_transport()
        chan = transport.open_session(timeout=connect_timeout)
        try:
            logging.info(f"{self._ip} background_script: {bash_script}")
            chan.exec_command(command)
            status = chan.recv_exit_status()
            if status != 0:
                raise RuntimeError(f"Failed running '{bash_script}', status '{status}'")
        finally:
            chan.close()
