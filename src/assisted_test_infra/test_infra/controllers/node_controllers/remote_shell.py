from paramiko import SSHException
from scp import SCPException

from assisted_test_infra.test_infra.controllers.node_controllers import ssh
from service_client import log


class RemoteShell:
    """Remote shell class used for running remote commands
    Open ssh connection to node and run command.
    """

    def __init__(self, ipv4_address, private_ssh_key_path, username="root"):
        self._ipv4_address = ipv4_address
        self._private_ssh_key_path = private_ssh_key_path
        self._username = username
        self.connection = self.connect_remote()

    def connect_remote(self):
        try:
            self.connection = ssh.SshConnection(
                self.ipv4_address, private_ssh_key_path=self.private_ssh_key_path, username=self.username
            )
            self.connection.connect()
            log.info(f"Successfully connect to remote shell: {self.ipv4_address}")
            return self.connection

        except (TimeoutError, SCPException, SSHException) as e:
            log.warning(f"Could not SSH through IP: {self.ipv4_address}, {str(e)}")
            raise

    def close_remote(self):
        if self.connection:
            if self.connection.ssh_client:
                self.connection.ssh_client.close()
                self.connection.ssh_client = None
                self.connection = None

    @property
    def ipv4_address(self):
        return self._ipv4_address

    @ipv4_address.setter
    def ipv4_address(self, ipv4_address):
        self._ipv4_address = ipv4_address

    @property
    def private_ssh_key_path(self):
        return self._private_ssh_key_path

    @private_ssh_key_path.setter
    def private_ssh_key_path(self, private_key):
        self._private_ssh_key_path = private_key

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, user):
        self._username = user

    def run_command(self, bash_command, raise_errors=True, timeout=180):
        """run_command should be similar to utils.run_command it is going to replace the command
        When needed remote shell results like utils.run_command because its used by other services
        as iptables , virsh command, date and more.
        :param bash_command:
        :param raise_errors:
        :param timeout:
        :return:
        """
        output = ""
        stderr = ""
        status = ""
        if isinstance(bash_command, list):
            bash_command = " ".join(bash_command)
        try:
            stdin, stdout, stderr = self.connection.ssh_client.exec_command(bash_command, timeout=timeout)
            status = stdout.channel.recv_exit_status()
            output = stdout.readlines()
            output = "".join(output)
            log.info(f"{self.ipv4_address} run_command: {bash_command} output: {output}")
        except RuntimeError:
            if raise_errors:
                raise

        return output, stderr, status

    @staticmethod
    def _get_directory_from_path(file_path):
        file_path = file_path.split("/")[:-1]
        return "/".join(file_path)

    def upload_file(self, local_source_path, remote_target_path):
        remote_dir = self._get_directory_from_path(remote_target_path)
        self.connection.execute(f"mkdir -p {remote_dir}")
        return self.connection.upload_file(local_source_path, remote_target_path)

    def download_file(self, remote_source_path, local_target_path):
        return self.connection.download_file(remote_source_path, local_target_path)
