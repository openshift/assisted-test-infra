from abc import ABC
from dataclasses import dataclass
from typing import List

from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig


@dataclass
class BaseOciConfig(BaseNodesConfig, ABC):
    oci_compartment_oicd: str = None
    oci_dns_zone: str = None
    oci_user_oicd: str = None
    oci_private_key_path: str = None
    oci_key_fingerprint: str = None
    oci_tenancy_oicd: str = None
    oci_region: str = None
    oci_vcn_oicd: str = None
    oci_public_subnet_oicd: str = None
    oci_private_subnet_oicd: str = None
    oci_extra_node_nsg_oicds: List[str] = None
    oci_extra_lb_nsg_oicds: List[str] = None
