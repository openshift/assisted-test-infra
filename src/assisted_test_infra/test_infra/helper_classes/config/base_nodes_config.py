import warnings
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from assisted_service_client import models

import consts

from .base_config import BaseConfig


@dataclass
class BaseNodesConfig(BaseConfig, ABC):
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
    master_boot_devices: List[str] = None  # order of boot devices to use

    worker_memory: int = None
    worker_vcpu: int = None
    workers_count: int = None
    worker_cpu_mode: str = None
    worker_disk: int = None
    worker_disk_size_gib: str = None  # disk size in GB.
    worker_disk_count: int = None
    worker_boot_devices: List[str] = None

    arbiter_memory: int = None
    arbiter_vcpu: int = None
    arbiters_count: int = None
    arbiter_cpu_mode: str = None
    arbiter_disk: int = None
    arbiter_disk_size_gib: str = None  # disk size in GB.
    arbiter_disk_count: int = None
    arbiter_boot_devices: List[str] = None

    api_vips: List[models.ApiVip] = None
    ingress_vips: List[models.IngressVip] = None
    base_cluster_domain: Optional[str] = None

    network_mtu: int = None
    tf_platform: str = (
        None  # todo - make all tf dependent platforms (e.g. vsphere, nutanix) inherit from BaseTerraformConfig  # noqa E501
    )

    @property
    def nodes_count(self):
        if self.workers_count is not None and self.masters_count is not None:
            arbiters = self.arbiters_count or 0
            return self.masters_count + self.workers_count + arbiters

        return 0

    @nodes_count.setter
    def nodes_count(self, nodes_count: int):
        warnings.warn(
            "Setting nodes_count is deprecated. nodes_count value is taken from masters_count plus"
            " workers_count instead.",
            DeprecationWarning,
        )
