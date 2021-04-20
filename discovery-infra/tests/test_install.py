from typing import Optional

import pytest

from test_infra import consts, utils
from test_infra._config import Config
from test_infra.assisted_service_api import InventoryClient
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.nodes import Nodes
from tests.base_test import BaseTest
from tests.conftest import get_available_openshift_versions

from junit_report import JunitTestSuite


class BaseTestHelper:

    @staticmethod
    def prepare_for_install(cluster: Cluster,
                            nodes: Nodes,
                            iso_download_path=Config.get("iso_download_path"),
                            iso_image_type=Config.get("iso_image_type"),
                            nodes_count=Config.get("num_nodes"),
                            vip_dhcp_allocation=Config.get("vip_dhcp_allocation"),
                            download_image=Config.get("download_image"),
                            platform=Config.get("platform"),
                            static_ips_config=None,
                            is_ipv6=Config.get("is_ipv6"),
                            service_network_cidr=Config.get("service_cidr"),
                            cluster_network_cidr=Config.get("cluster_cidr"),
                            cluster_network_host_prefix=Config.get("host_prefix"),
                            ):
        cluster.prepare_for_install(nodes=nodes,
                                    iso_download_path=iso_download_path,
                                    iso_image_type=iso_image_type,
                                    nodes_count=nodes_count,
                                    vip_dhcp_allocation=vip_dhcp_allocation,
                                    download_image=download_image,
                                    platform=platform,
                                    static_ips_config=static_ips_config,
                                    is_ipv6=is_ipv6,
                                    service_network_cidr=service_network_cidr,
                                    cluster_network_cidr=cluster_network_cidr,
                                    cluster_network_host_prefix=cluster_network_host_prefix,
                                    )


class TestInstall(BaseTest, BaseTestHelper):

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, nodes: Nodes, cluster, openshift_version):
        new_cluster = cluster(openshift_version=openshift_version)
        self.prepare_for_install(new_cluster, nodes)
        new_cluster.start_install_and_wait_for_installed(Config.get("num_nodes"))

        # new_cluster.prepare_for_install(nodes, *Config.get_group("iso_download_path", "iso_image_type",
        #                                                          "num_nodes", "vip_dhcp_allocation",
        #                                                          "download_image", "platform", "is_ipv6",
        #                                                          "service_cidr", "cluster_cidr", "host_prefix"))