import pytest
from collections import Counter
import logging
from test_infra.consts import NodeRoles
from tests.base_test import BaseTest


class TestRoleSelection(BaseTest):
    @pytest.mark.regression
    def test_automatic_role_assignment(self, nodes, cluster):
        """Let the system automatically assign all roles in a satisfying environment."""
        new_cluster = cluster()

        logging.info(new_cluster.setup_nodes(nodes))
        new_cluster.set_network_params(nodes.controller)
        new_cluster.wait_for_ready_to_install()
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress()

        host_assignments = new_cluster.get_host_assigned_roles()

        assert Counter(host_assignments.values()) == Counter(master=3, worker=2)

    @pytest.mark.regression
    def test_partial_role_assignment(self, nodes, cluster):
        """Let the system semi-automatically assign roles in a satisfying environment."""
        new_cluster = cluster()

        new_cluster.setup_nodes(nodes)
        new_cluster.set_network_params(nodes.controller)
        new_cluster.wait_for_ready_to_install()

        manually_assigned_roles = new_cluster.set_host_roles(requested_roles=Counter(master=1, worker=1))
        new_cluster.start_install()
        new_cluster.wait_for_installing_in_progress()
        actual_assignments = new_cluster.get_host_assigned_roles()

        assert Counter(actual_assignments.values()) == Counter(master=3, worker=2)
        assert set(tuple(a.values()) for a in manually_assigned_roles) <= set(actual_assignments.items())
