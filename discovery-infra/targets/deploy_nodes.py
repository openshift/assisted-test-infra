#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse

from targets.target import Target
from test_infra.controllers.nat_controller import NatController
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.nodes import Nodes
from test_infra.factory import cluster_factory, nodes_factory


class DeployNodes(Target):

    def __init__(self):
        super().__init__()
        nat_interfaces = (self._terraform_config.net_asset.libvirt_network_if,
                          self._terraform_config.net_asset.libvirt_secondary_network_if)
        self._nat = NatController(nat_interfaces)
        self._nodes: Nodes = nodes_factory(self._terraform_config, self._nat)
        self._cluster: Cluster = cluster_factory(self._nodes, self._api_client, self._cluster_config)

    def run(self):
        self._cluster.prepare_for_installation()


class DeployNodesWithInstall(DeployNodes):
    def run(self):
        super().run()
        self._cluster.start_install_and_wait_for_installed()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Deploy nodes")
    parser.add_argument("-i", "--install", help="Install flag", type=bool, nargs='?', default=False, const=True)

    args = parser.parse_args()
    if args.install:
        DeployNodesWithInstall().run()
    else:
        DeployNodes().run()
