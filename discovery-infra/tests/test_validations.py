import pytest

from test_infra import consts
from tests.base_test import BaseTest
from tests.conftest import env_variables
from assisted_service_client.rest import ApiException


@pytest.mark.validations
class TestValidations(BaseTest):
    def _wait_and_kill_installer(self, cluster, nodes, host):
        # Wait for specific host to be in installing in progress
        cluster.wait_for_specific_host_status(host=host,
                                              statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS])
        # Kill master installer to simulate host error
        selected_node = nodes.get_node_from_cluster_host(host)
        selected_node.kill_installer()

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
        self.assert_cluster_validation(orig_cluster, "network", "api-vip-defined", "failure")
        self.assert_cluster_validation(orig_cluster, "network", "api-vip-valid", "pending")
        self.assert_cluster_validation(orig_cluster, "network", "ingress-vip-defined", "failure")
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
        ram_node.set_ram_kib(3145728)  # 3GB
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

    @pytest.mark.regression
    def test_cluster_nodes_count(self, nodes, cluster):
        # This test check that cluster has exactly 3 master nodes, or 3 masters and more then 1 workers.

        # Define new cluster
        new_cluster = cluster()
        # Wait for cluster to be in Ready to install (with 3 masters and 2 workers)
        new_cluster.prepare_for_install(nodes=nodes)
        cluster_details = new_cluster.get_details()
        self.assert_cluster_validation(cluster_details, "hosts-data", "sufficient-masters-count", "success")
        # set master role to a worker host
        random_worker = new_cluster.get_random_host_by_role(role=consts.NodeRoles.WORKER)
        new_cluster.set_specific_host_role(random_worker, role=consts.NodeRoles.MASTER)
        new_cluster.wait_for_cluster_validation("hosts-data", "sufficient-masters-count", ["failure"])
        # set back worker role
        new_cluster.set_specific_host_role(random_worker, role=consts.NodeRoles.WORKER)
        new_cluster.wait_for_cluster_validation("hosts-data", "sufficient-masters-count", ["success"])
        # Disable the first worker node
        worker_hosts = new_cluster.get_hosts_by_role(role=consts.NodeRoles.WORKER)
        worker_host1 = worker_hosts[0]
        worker_host2 = worker_hosts[1]
        new_cluster.disable_host(host=worker_host1)
        cluster_details = new_cluster.get_details()
        self.assert_cluster_validation(cluster_details, "hosts-data", "sufficient-masters-count", "failure")
        # Disable the second worker node
        new_cluster.disable_host(host=worker_host2)
        new_cluster.wait_for_ready_to_install()
        cluster_details = new_cluster.get_details()
        self.assert_cluster_validation(cluster_details, "hosts-data", "sufficient-masters-count", "success")
        # Disable master node
        master_host = new_cluster.get_random_host_by_role(role=consts.NodeRoles.MASTER)
        new_cluster.disable_host(host=master_host)
        cluster_details = new_cluster.get_details()
        self.assert_cluster_validation(cluster_details, "hosts-data", "sufficient-masters-count", "failure")

    @pytest.mark.regression
    def test_cluster_error_when_master_in_error(self, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()
        # Start cluster install
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        # Wait for specific master to be in installing in progress
        master_host = new_cluster.get_random_host_by_role(consts.NodeRoles.MASTER)
        self._wait_and_kill_installer(new_cluster, nodes, master_host)
        # Wait for host Error
        new_cluster.wait_for_host_status([consts.NodesStatus.ERROR])
        # Wait for Cluster status: Error
        new_cluster.wait_for_cluster_in_error_status()

    @pytest.mark.regression
    def test_cluster_error_when_two_worker_in_error(self, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()
        # Start cluster install
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        # Wait for both workers to be in installing in progress, and kill installer
        worker_hosts = new_cluster.get_hosts_by_role(role=consts.NodeRoles.WORKER)
        worker_host1 = worker_hosts[0]
        worker_host2 = worker_hosts[1]
        self._wait_and_kill_installer(new_cluster, nodes, worker_host1)
        self._wait_and_kill_installer(new_cluster, nodes, worker_host2)
        # Wait for Hosts status: Error
        new_cluster.wait_for_host_status(statuses=[consts.NodesStatus.ERROR],
                                         nodes_count=2,
                                         fall_on_error_status=False)
        # Wait for Cluster status: Error
        new_cluster.wait_for_cluster_in_error_status()

    @pytest.mark.regression
    def test_installation_success_while_one_worker_error(self, nodes, cluster):
        # Define new cluster
        new_cluster = cluster()
        # Start cluster install
        new_cluster.prepare_for_install(nodes=nodes)
        new_cluster.start_install()
        # Wait for specific worker to be in installing in progress, and kill installer
        worker_host = new_cluster.get_random_host_by_role(consts.NodeRoles.WORKER)
        self._wait_and_kill_installer(new_cluster, nodes, worker_host)
        # Wait for node Error
        new_cluster.wait_for_host_status([consts.NodesStatus.ERROR], fall_on_error_status=False)
        # Wait for nodes to install
        new_cluster.wait_for_hosts_to_install(nodes_count=4, fall_on_error_status=False)
        new_cluster.wait_for_install()
