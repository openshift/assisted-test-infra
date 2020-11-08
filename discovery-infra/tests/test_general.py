from tempfile import NamedTemporaryFile

import consts
import pytest
from assisted_service_client.rest import ApiException

from tests.base_test import BaseTest, random_name


class TestGeneral(BaseTest):
    def test_create_cluster(self, api_client, cluster):
        c = cluster()
        assert c.id in map(lambda cluster: cluster['id'], api_client.clusters_list())
        assert api_client.cluster_get(c.id)
        assert api_client.get_events(c.id)

    def test_delete_cluster(self, api_client, cluster):
        c = cluster()
        assert api_client.cluster_get(c.id)
        api_client.delete_cluster(c.id)

        assert c.id not in map(lambda cluster: cluster['id'], api_client.clusters_list())

        with pytest.raises(ApiException):
            assert api_client.cluster_get(c.id)

    @pytest.mark.xfail
    def test_cluster_unique_name(self, api_client, cluster):
        cluster_name = random_name()

        _ = cluster(cluster_name)

        with pytest.raises(ApiException):
            cluster(cluster_name)

    def test_discovery(self, api_client, cluster, nodes):
        cluster_id = cluster().id
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        nodes.start_all()
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        return cluster_id

    def test_select_roles(self, api_client, cluster, nodes):
        cluster_id = self.test_discovery(api_client, cluster, nodes)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        hosts = api_client.get_cluster_hosts(cluster_id=cluster_id)
        for node in hosts:
            hostname = node["requested_hostname"]
            role = node["role"]
            if "master" in hostname:
                assert role == consts.NodeRoles.MASTER
            elif "worker" in hostname:
                assert role == consts.NodeRoles.WORKER
