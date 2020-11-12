import logging
import os
import random
import yaml
from contextlib import suppress
from string import ascii_lowercase
from typing import Optional
from collections import Counter

import pytest
from assisted_service_client.rest import ApiException
from test_infra import consts, utils
from test_infra.helper_classes.cluster import Cluster
from test_infra.helper_classes.nodes import Nodes
from tests.conftest import env_variables


def random_name():
    return ''.join(random.choice(ascii_lowercase) for i in range(10))


class BaseTest:

    @pytest.fixture(scope="function")
    def nodes(self, setup_node_controller):
        controller = setup_node_controller
        nodes = Nodes(controller, env_variables["private_ssh_key_path"])
        nodes.set_correct_boot_order(start_nodes=False)
        yield nodes
        nodes.shutdown_all()
        nodes.format_all_disks()

    @pytest.fixture()
    def cluster(self, api_client):
        clusters = []

        def get_cluster_func(cluster_name: Optional[str] = None):
            if not cluster_name:
                cluster_name = random_name()

            res = Cluster(api_client=api_client, cluster_name=cluster_name)
            clusters.append(res)
            return res

        yield get_cluster_func

        for cluster in clusters:
            logging.info(f'--- TEARDOWN --- deleting created cluster {cluster.id}\n')
            if cluster.is_installing():
                cluster.cancel_install()

            with suppress(ApiException):
                cluster.delete()

    @staticmethod
    def get_cluster_by_name(api_client, cluster_name):
        clusters = api_client.clusters_list()
        for cluster in clusters:
            if cluster['name'] == cluster_name:
                return cluster
        return None

    @staticmethod
    def assert_http_error_code(api_call, status, reason, **kwargs):
        with pytest.raises(ApiException) as response:
            api_call(**kwargs)
        assert response.value.status == status
        assert response.value.reason == reason
