import pytest

from tests.conftest import env_variables, is_qe_env
from tests.base_test import BaseTest


class TestDHCP(BaseTest):
    def test_unique_vip_hostname(self, api_client, cluster, nodes):
        vips = []

        # First time
        first_cluster = cluster()
        first_cluster.prepare_for_install(nodes=nodes, vip_dhcp_allocation=True)
        vips.append(self._get_api_vip(nodes.controller))

        first_cluster.delete()
        nodes.controller.destroy_all_nodes()

        # Second time
        nodes.controller.prepare_nodes()
        second_cluster = cluster()
        second_cluster.prepare_for_install(nodes=nodes, vip_dhcp_allocation=True)
        vips.append(self._get_api_vip(nodes.controller))

        assert vips[0]['hostname'] != vips[1]['hostname']

    def _get_api_vip(self, controller):
        leases = controller.list_leases(controller.network_name)
        assert leases
        lease_api = list(filter(lambda lease: lease['hostname'].endswith('api'), leases))
        assert len(lease_api) == 1

        return lease_api[0]
