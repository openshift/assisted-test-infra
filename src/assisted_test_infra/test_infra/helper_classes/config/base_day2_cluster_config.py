from abc import ABC
from dataclasses import dataclass
from typing import Optional

from assisted_service_client import models

from assisted_test_infra.test_infra import helper_classes
from assisted_test_infra.test_infra.helper_classes.config.base_cluster_config import BaseClusterConfig


@dataclass
class BaseDay2ClusterConfig(BaseClusterConfig, ABC):
    day1_cluster: Optional["helper_classes.cluster.Cluster"] = None
    day1_cluster_details: Optional[models.cluster.Cluster] = None
    day1_base_cluster_domain: Optional[str] = None
    day1_api_vip_dnsname: Optional[str] = None
    day2_workers_count: Optional[int] = None
    day2_cpu_architecture: Optional[str] = None
    infra_env_id: Optional[str] = None
    tf_folder: Optional[str] = None
