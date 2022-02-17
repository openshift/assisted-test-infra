import warnings
from abc import ABC
from dataclasses import dataclass
from pathlib import Path

import consts

from .base_config import BaseConfig


@dataclass
class BaseNodeConfig(BaseConfig, ABC):
    platform: str = None
    is_ipv4: bool = None
    is_ipv6: bool = None
    bootstrap_in_place: bool = None
    private_ssh_key_path: Path = None
    working_dir: str = consts.WORKING_DIR

    master_memory: int = None
    master_vcpu: int = None
    masters_count: int = None
    master_cpu_mode: str = None
    master_disk: int = None  # disk size in MB.
    master_disk_size_gib: str = None  # disk size in GB.
    master_disk_count: int = None  # number of disks to create

    worker_memory: int = None
    worker_vcpu: int = None
    workers_count: int = None
    worker_cpu_mode: str = None
    worker_disk: int = None
    worker_disk_size_gib: str = None  # disk size in GB.
    worker_disk_count: int = None

    network_mtu: int = None

    @property
    def nodes_count(self):
        if self.workers_count is not None and self.masters_count is not None:
            return self.masters_count + self.workers_count

        return 0

    @nodes_count.setter
    def nodes_count(self, nodes_count: int):
        warnings.warn(
            "Setting nodes_count is deprecated. nodes_count value is taken from masters_count plus"
            " workers_count instead.",
            DeprecationWarning,
        )
