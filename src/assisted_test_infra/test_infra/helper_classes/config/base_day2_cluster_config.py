from abc import ABC
from dataclasses import dataclass

from assisted_test_infra.test_infra.helper_classes.config.base_cluster_config import BaseClusterConfig


@dataclass
class BaseDay2ClusterConfig(BaseClusterConfig, ABC):
    day1_cluster_id: str = None
    day1_cluster_name: str = None
    day2_workers_count: int = None
    infra_env_id: str = None
    tf_folder: str = None
    day2_workers_arch: str = None
    day2_worker_remote_libvirt_uri: str = None
    day2_worker_remote_libvirt_network_prefix: str = None
