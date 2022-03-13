from abc import ABC
from dataclasses import dataclass

from assisted_test_infra.test_infra.helper_classes.config.controller_config import BaseNodeConfig


@dataclass
class BaseVSphereConfig(BaseNodeConfig, ABC):
    vsphere_vcenter: str = None
    vsphere_username: str = None
    vsphere_password: str = None
    vsphere_cluster: str = None
    vsphere_datacenter: str = None
    vsphere_datastore: str = None
    vsphere_network: str = None

    def __post_init__(self):
        super().__post_init__()
