from tempfile import NamedTemporaryFile

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

    def test_discovery(self, api_client, cluster, node_controller):
        cluster_id = cluster().id
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        node_controller.start_all_nodes()
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
