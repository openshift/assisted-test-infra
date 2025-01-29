from assisted_test_infra.test_infra import utils
from service_client import log


class Iqn:

    def __init__(self, unique_name: str, year_month: str = "2024-11", base_domain: str = "example.com"):
        self.year_month = year_month
        # base domain set in reverse order.
        self.base_domain = ".".join(reversed(base_domain.split(".")))
        # node name + disk index may be used test-infra-cluster-4a25cd51-master-0-disk-0
        self.unique_name = unique_name

    def __repr__(self):
        return f"iqn.{self.year_month}.{self.base_domain}:{self.unique_name}"

    def __str__(self):
        return f"iqn.{self.year_month}.{self.base_domain}:{self.unique_name}"


class Receiver:

    def __init__(self, fn_callback, **defaults_kwargs):
        self.fn_callback = fn_callback
        self.defaults_kwargs = defaults_kwargs

    def execute(self, *args, **kwargs):
        self.defaults_kwargs.update(kwargs)
        log.info(f"iscsi_target exec: {str(args)} {str(kwargs)}")
        self.fn_callback(*args, **kwargs)


class IscsiTargetConfig:
    def __init__(
        self, disk_name: str, disk_size_gb: int, iqn: Iqn, remote_iqn: Iqn, iso_disk_copy: str, servers: list[str]
    ):
        self._disk_name = disk_name
        self._disk_size = disk_size_gb
        self._iqn = iqn
        self._data_file = iso_disk_copy
        self._remote_iqn = remote_iqn
        self._servers = servers

    @property
    def disk_name(self):
        return self._disk_name

    @property
    def disk_size(self):
        return self._disk_size

    @property
    def iqn(self):
        return self._iqn

    @property
    def data_file(self):
        return self._data_file

    @property
    def remote_iqn(self):
        return self._remote_iqn

    @property
    def servers(self):
        return self._servers


class IscsiTargetController:

    def __new__(cls):
        # Make The controller singleton class because managed by hypervisor as a single service
        if not hasattr(cls, "instance"):
            log.info("Creating singleton IscsiTargetController instance")
            cls.instance = super(IscsiTargetController, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        self.builder = IscsiBuilder(Receiver(utils.run_command, shell=True))
        self._target_configs = []

    def create_target(self, config: IscsiTargetConfig, clear_config=False) -> None:
        if clear_config:
            self.builder.clear_iscsi_target_config()
        # append target configs to delete on cleanup
        self._target_configs.append(config)

        self.builder.remove_file_disk(config.disk_name)
        self.builder.create_file_disk(config.disk_name, config.disk_size)
        self.builder.create_file_io(config.disk_name, config.disk_size)
        self.builder.create_iqn(config.iqn)
        self.builder.create_lun(config.iqn, config.disk_name)
        self.builder.create_portal(config.iqn, config.servers)
        self.builder.create_access_list(config.iqn, config.remote_iqn)
        self.builder.create_access_list_data_out(config.iqn, config.remote_iqn)
        self.builder.create_access_list_nopin_timeout(config.iqn, config.remote_iqn)
        self.builder.save_config()
        self.builder.copy_to_created_disk(config.disk_name, config.data_file)

    def clean_target(self) -> None:
        for config in self._target_configs:
            # Remove resource file created
            self.builder.remove_file_disk(config.disk_name)
        self.builder.clear_iscsi_target_config()


class IscsiBuilder:
    """iSCSI builder implements commands on the receiver (ssh runner).

    The builder can run on any machine with targetcli installed
    Iscsi configuration:
    https://manpages.ubuntu.com/manpages/focal/man8/targetcli.8.html
    """

    service_cmd = "targetcli"

    def __init__(self, receiver):
        self.receiver = receiver

    def remove_file_disk(self, disk_name):
        self.receiver.execute(f"rm -rf  /tmp/{disk_name}")

    def create_file_disk(self, disk_name: str, disk_size_gb: int, type_: str = "raw") -> None:
        self.receiver.execute(f"qemu-img create  -f {type_} /tmp/{disk_name} {str(disk_size_gb)}G")

    def clear_iscsi_target_config(self) -> None:
        cmd = f"{self.service_cmd} clearconfig confirm=True"
        self.receiver.execute(cmd)

    def create_file_io(self, disk_name: str, disk_size: int) -> None:
        cmd = (
            f"{self.service_cmd} backstores/fileio create name={disk_name}"
            f" size={str(disk_size)}G file_or_dev=/tmp/{disk_name}"
        )
        self.receiver.execute(cmd)

    def create_iqn(self, iqn: Iqn) -> None:
        cmd = f"{self.service_cmd} /iscsi create {str(iqn)}"
        self.receiver.execute(cmd)

    def create_lun(self, iqn: Iqn, disk_name: str) -> None:
        cmd = f"{self.service_cmd} /iscsi/{str(iqn)}/tpg1/luns create /backstores/fileio/{disk_name}"
        self.receiver.execute(cmd)

    def create_portal(self, iqn: Iqn, server_addresses: list[str], port: int = 3260) -> None:
        # To enable multipath - set additional server addresses . by default 0.0.0.0 3260 exists.
        cmd_delete = f"{self.service_cmd} /iscsi/{str(iqn)}/tpg1/portals delete 0.0.0.0 {port}"
        self.receiver.execute(cmd_delete, raise_errors=False)
        for server in server_addresses:
            cmd = f"{self.service_cmd} /iscsi/{str(iqn)}/tpg1/portals create {server} {port}"
            self.receiver.execute(cmd)

    def create_access_list(self, iqn: Iqn, remote_iqn: Iqn) -> None:
        cmd = f"{self.service_cmd} /iscsi/{str(iqn)}/tpg1/acls create {str(remote_iqn)}"
        self.receiver.execute(cmd)

    def create_access_list_data_out(self, iqn: Iqn, remote_iqn: Iqn, timeout: int = 60, retries: int = 10) -> None:
        cmd = f"{self.service_cmd} /iscsi/{str(iqn)}/tpg1/acls/{str(remote_iqn)}/ "
        for param in [f"set attribute dataout_timeout={timeout}", f"set attribute dataout_timeout_retries={retries}"]:
            self.receiver.execute(cmd + param)

    def create_access_list_nopin_timeout(self, iqn: Iqn, remote_iqn: Iqn, timeout: int = 60) -> None:
        cmd = f"{self.service_cmd} /iscsi/{str(iqn)}/tpg1/acls/{str(remote_iqn)}/ "
        for param in [f"set attribute nopin_timeout={timeout}", f"set attribute nopin_response_timeout={timeout}"]:
            self.receiver.execute(cmd + param)

    def save_config(self):
        cmd = f"{self.service_cmd} / saveconfig"
        self.receiver.execute(cmd)

    def copy_to_created_disk(self, disk_name: str, data_disk_file: str) -> None:
        cmd = f"dd conv=notrunc if={data_disk_file} of=/tmp/{disk_name}"
        self.receiver.execute(cmd)
