from dataclasses import dataclass

from assisted_test_infra.test_infra.helper_classes.config.controller_config import BaseNodeConfig


@dataclass
class BaseVSphereConfig(BaseNodeConfig):
    vsphere_vcenter: str = None
    vsphere_username: str = None
    vsphere_password: str = None
    vsphere_cluster: str = None
    vsphere_datacenter: str = None
    vsphere_datastore: str = None
    vsphere_network: str = None
    vsphere_parent_folder: str = None
    vsphere_folder: str = None
