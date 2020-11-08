from collections import Counter

from consts import NodeRoles
from tests.base_test import BaseTest


class TestRoleSelection(BaseTest):
    def test_automatic_role_assignment(self, api_client, nodes, cluster):
        """Let the system automatically assign all roles in a satisfying environment."""
        cluster_id = cluster().id

        self.setup_hosts(cluster_id=cluster_id,
                         api_client=api_client,
                         nodes=nodes)
        self.set_network_params(cluster_id=cluster_id,
                                api_client=api_client,
                                controller=nodes.controller)

        self.expect_ready_to_install(cluster_id=cluster_id,
                                     api_client=api_client)
        actual_assignments = self.start_installation(cluster_id=cluster_id,
                                                     api_client=api_client)

        assert Counter(actual_assignments.values()) == Counter(master=3, worker=2)

    def test_partial_role_assignment(self, api_client, nodes, cluster):
        """Let the system semi-automatically assign roles in a satisfying environment."""
        cluster_id = cluster().id

        hosts = self.setup_hosts(cluster_id=cluster_id,
                                 api_client=api_client,
                                 nodes=nodes)
        self.set_network_params(cluster_id=cluster_id,
                                api_client=api_client,
                                controller=nodes.controller)
        self.expect_ready_to_install(cluster_id=cluster_id,
                                     api_client=api_client)
        manually_assigned_roles = self.assign_roles(cluster_id=cluster_id,
                                                    api_client=api_client,
                                                    hosts=hosts,
                                                    requested_roles=Counter(master=1, worker=1))
        actual_assignments = self.start_installation(cluster_id=cluster_id,
                                                     api_client=api_client)

        assert Counter(actual_assignments.values()) == Counter(master=3, worker=2)
        assert set(tuple(a.values()) for a in manually_assigned_roles) <= set(actual_assignments.items())
