import pytest

from tests.base_test import BaseTest

class TestCancelReset(BaseTest):
    @pytest.mark.regression
    def test_cancel_reset_after_node_boot(self, api_client, node_controler):
    # Define new cluster
        cluster_id = self.create_cluster(api_client=api_client).id
    # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
    # Boot nodes into ISO
        node_controler.start_all_nodes()
    # Wait untill hosts are disovered and update host roles
        self.wait_untill_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_ingress_and_api_vips(cluster_id=cluster_id,
        api_client=api_client, 
        controler=node_controler
    )
    #Start cluster install
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
    #Cancel cluster install once at least one host booted
        self.wait_for_one_host_to_boot_durring_install(cluster_id=cluster_id, api_client=api_client)
        self.cancel_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_cancelled_status(
            cluster_id=cluster_id, 
            api_client=api_client
        )
    #Reset cluster install
        self.reset_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_insufficient_status(
            cluster_id=cluster_id, 
            api_client=api_client
        )
    #Reboot requiered nodes into ISO
        self.reboot_required_nodes_into_iso_after_reset(
            cluster_id=cluster_id, 
            api_client=api_client, 
            controler=node_controler
        )

    #Wait for hosts to be rediscovered 
        self.wait_untill_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.wait_untill_cluster_is_ready_for_install(cluster_id=cluster_id, api_client=api_client)
    #Install Cluster
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)


