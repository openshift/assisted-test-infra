import random
import pytest

from test_infra import consts
from tests.base_test import BaseTest
from tests.conftest import env_variables
from assisted_service_client.rest import ApiException


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

    @pytest.mark.regression
    @pytest.mark.skip(reason="BZ:1897916")
    def test_hosts_and_cluster_max_length(self, cluster, nodes):
        # This test check installation with max cluster name length (54),
        # and max host name length (63)

        # Trying to create a cluster with more then 54 chars
        cluster_name = "this-is-a-very-long-cluster-name-this-is-a-very-long-cluster-name-this-is-a-very"
        self.assert_string_length(cluster_name, 80)
        # TODO: assert on error code and reason
        with pytest.raises(ApiException):
            cluster(cluster_name)
        c = cluster()
        # Trying to update cluster name to have more then 54 chars
        with pytest.raises(ApiException):
            c.set_cluster_name(cluster_name)
        # Set cluster name with exactly 54 chars
        cluster_name = "this-is-exactly-54-chars-cluster-name-for-testing-abcd"
        self.assert_string_length(cluster_name, 54)
        c.set_cluster_name(cluster_name)
        c.prepare_for_install(nodes=nodes)
        random_master_host = c.get_random_host_by_role(role=consts.NodeRoles.MASTER)
        # Trying to set host name with more than 63 chars
        long_hostname = "this-is-a-more-than-63chars-long-host-name-this-is-more-than-63chars-long-host12"
        self.assert_string_length(long_hostname, 80)
        with pytest.raises(ApiException):
            c.set_host_name(host_id=random_master_host["id"], requested_name=long_hostname)
        # Set host name with exactly 63 chars
        long_hostname = "this-is-a-63chars-long-host-name-this-is-a-63chars-long-host-12"
        self.assert_string_length(long_hostname, 63)
        c.set_host_name(host_id=random_master_host["id"], requested_name=long_hostname)
        c.start_install_and_wait_for_installed()
