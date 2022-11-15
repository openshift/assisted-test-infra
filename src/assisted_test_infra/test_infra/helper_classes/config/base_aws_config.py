from abc import ABC
from dataclasses import dataclass

from assisted_test_infra.test_infra.helper_classes.config.base_cluster_config import BaseClusterConfig
from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig


@dataclass
class BaseAwsConfig(BaseNodesConfig, BaseClusterConfig, ABC):
    ipxe_script: str = None
    job_id: str = "changeme"  # TODO: Propagate job_id here
