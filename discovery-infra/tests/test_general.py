import consts
import pytest
from assisted_service_client.rest import ApiException

from tests.base_test import BaseTest, random_name


class TestGeneral(BaseTest):
    @pytest.mark.regression
    def test_create_cluster(self, api_client, cluster):
        c = cluster()
        assert c.id in map(lambda cluster: cluster['id'], api_client.clusters_list())
        assert api_client.cluster_get(c.id)
        assert api_client.get_events(c.id)

    @pytest.mark.regression
    def test_delete_cluster(self, api_client, cluster):
        c = cluster()
        assert api_client.cluster_get(c.id)
        api_client.delete_cluster(c.id)

        assert c.id not in map(lambda cluster: cluster['id'], api_client.clusters_list())

        with pytest.raises(ApiException):
            assert api_client.cluster_get(c.id)

    @pytest.mark.xfail
    @pytest.mark.regression
    def test_cluster_unique_name(self, api_client, cluster):
        cluster_name = random_name()

        _ = cluster(cluster_name)

        with pytest.raises(ApiException):
            cluster(cluster_name)

    def test_discovery(self, api_client, cluster, nodes):
        c = cluster()
        c.generate_and_download_image()
        nodes.start_all()
        c.wait_until_hosts_are_discovered()
        return c

    @pytest.mark.regression
    def test_select_roles(self, api_client, cluster, nodes):
        c = self.test_discovery(api_client, cluster, nodes)
        c.set_host_roles()
        hosts = c.get_hosts()
        for host in hosts:
            hostname = host["requested_hostname"]
            role = host["role"]
            if "master" in hostname:
                assert role == consts.NodeRoles.MASTER
            elif "worker" in hostname:
                assert role == consts.NodeRoles.WORKER
