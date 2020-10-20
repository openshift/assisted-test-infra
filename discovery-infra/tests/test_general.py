import pytest
from assisted_service_client.rest import ApiException
from tempfile import NamedTemporaryFile

from tests.base_test import BaseTest, random_name


class TestGeneral(BaseTest):
    def test_create_cluster(self, api_client, cluster):
        c = cluster()
        assert c.id in map(lambda cluster: cluster['id'], api_client.clusters_list())
        assert api_client.cluster_get(c.id)

    def test_delete_cluster(self, api_client, cluster):
        c = cluster()
        assert api_client.cluster_get(c.id)
        api_client.delete_cluster(c.id)

        assert c.id not in map(lambda cluster: cluster['id'], api_client.clusters_list())

        with pytest.raises(ApiException):
            assert api_client.cluster_get(c.id)

    def test_cluster_unique_id(self, api_client, cluster):
        clusters = []

        for _ in range(3):
            clusters.append(cluster())

        cluster_ids = list(map(lambda c: c.id, clusters))
        assert len(set(cluster_ids)) == len(cluster_ids)

    def test_cluster_unique_name(self, api_client, cluster):
        cluster_name = random_name()

        _ = cluster(cluster_name)

        with pytest.raises(ApiException):
            cluster(cluster_name)
