from abc import ABC
from dataclasses import dataclass

from assisted_service_client import models

from assisted_test_infra.test_infra import helper_classes
from assisted_test_infra.test_infra.helper_classes.config.base_cluster_config import BaseClusterConfig


@dataclass
class BaseDay2ClusterConfig(BaseClusterConfig, ABC):
    day1_cluster: "helper_classes.cluster.Cluster" = None
    day1_cluster_details: models.cluster.Cluster = None
    day1_base_cluster_domain: str = None
    day1_api_vip_dnsname: str = None
    day2_workers_count: int = None
    infra_env_id: str = None
    tf_folder: str = None
