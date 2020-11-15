import json
import pytest

from test_infra import consts
from tests.base_test import BaseTest
from tests.conftest import env_variables


class TestValidations(BaseTest):
    @pytest.mark.regression
    def test_basic_cluster_validations(self, cluster):
        new_cluster = cluster()

        # Check initial validations
        new_cluster.wait_for_pending_for_input_status()
        orig_cluster = new_cluster.get_details()
        self.assert_cluster_validation(orig_cluster, "configuration", "pull-secret-set", "success")
        self.assert_cluster_validation(orig_cluster, "hosts-data", "all-hosts-are-ready-to-install", "success")
        self.assert_cluster_validation(orig_cluster, "hosts-data", "sufficient-masters-count", "failure")
        self.assert_cluster_validation(orig_cluster, "network", "machine-cidr-defined", "failure")
        self.assert_cluster_validation(orig_cluster, "network", "machine-cidr-equals-to-calculated-cidr", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "api-vip-defined", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "api-vip-valid", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "ingress-vip-defined", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "ingress-vip-valid", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "dns-domain-defined", "success")
        self.assert_cluster_validation(orig_cluster, "network", "cluster-cidr-defined", "success")
        self.assert_cluster_validation(orig_cluster, "network", "service-cidr-defined", "success")
        self.assert_cluster_validation(orig_cluster, "network", "no-cidrs-overlapping", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "network-prefix-valid", "success")
        self.assert_cluster_validation(orig_cluster, "network", "ntp-server-configured", "success")

        # Check base DNS domain
        new_cluster.set_base_dns_domain("")
        new_cluster.wait_for_cluster_validation("network", "dns-domain-defined", ["failure"])
        new_cluster.set_base_dns_domain(orig_cluster.base_dns_domain)
        new_cluster.wait_for_cluster_validation("network", "dns-domain-defined", ["success"])

        # Check pull secret
        new_cluster.set_pull_secret("")
        new_cluster.wait_for_cluster_validation("configuration", "pull-secret-set", ["failure"])
        new_cluster.set_pull_secret(env_variables['pull_secret'])
        new_cluster.wait_for_cluster_validation("configuration", "pull-secret-set", ["success"])

    @pytest.fixture(scope="function")
    def modified_nodes(self, nodes):
        yield nodes
        nodes.run_for_all_nodes("reset_cpu_cores")
        nodes.run_for_all_nodes("reset_ram_kib")

    @pytest.mark.regression
    def test_host_insufficient(self, cluster, modified_nodes):
        new_cluster = cluster()
        new_cluster.generate_and_download_image()

        # Modify vCPU count on the first node to be insufficient
        vcpu_node = modified_nodes.nodes[0]
        vcpu_node.set_cpu_cores(1)
        vcpu_host_id = vcpu_node.get_host_id()

        # Modify RAM amount on the second node to be insufficient
        ram_node = modified_nodes.nodes[1]
        ram_node.set_ram_kib(2097152)  # 2GB
        ram_host_id = ram_node.get_host_id()

        modified_nodes.start_all()
        new_cluster.wait_until_hosts_are_discovered(allow_insufficient=True)
        new_cluster.wait_for_host_validation(vcpu_host_id, "hardware", "has-min-cpu-cores", ["failure"])
        new_cluster.wait_for_host_validation(ram_host_id, "hardware", "has-min-memory", ["failure"])

        # Return to original settings and verify that validations pass
        vcpu_node.shutdown()
        vcpu_node.reset_cpu_cores()
        vcpu_node.start()

        ram_node.shutdown()
        ram_node.reset_ram_kib()
        ram_node.start()

        new_cluster.wait_until_hosts_are_discovered(allow_insufficient=True)
        new_cluster.wait_for_host_validation(vcpu_host_id, "hardware", "has-min-cpu-cores", ["success"])
        new_cluster.wait_for_host_validation(ram_host_id, "hardware", "has-min-memory", ["success"])
