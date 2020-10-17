import pytest
import openshift as oc
from logger import log

from tests.base_test import BaseTest
from tests.conftest import env_variables


@pytest.mark.proxy
class TestProxy(BaseTest):
    def is_proxy_defined_in_install_config(self, cluster_id, api_client, http_proxy, https_proxy):
        install_config = self.get_cluster_install_config(cluster_id=cluster_id, api_client=api_client)
        log.info(f'Verifying proxy parameters are deinfied in install-config.yaml for Cluster {cluster_id}')
        assert install_config['proxy']['httpProxy'] == http_proxy
        assert install_config['proxy']['httpsProxy'] == https_proxy

    def are_proxy_paramas_defined_in_clusterwide_proxy(self, cluster_id, api_client, http_proxy, https_proxy):
        api_client.download_kubeconfig(cluster_id, env_variables['KUBECONFIG_PATH'])
        log.info(f'Verifying proxy parameters are deinfied in cluster wide proxy object for Cluster {cluster_id}')
        proxy_object = oc.selector('proxy/cluster').objects()[0]
        assert proxy_object.model.spec.httpProxy == http_proxy
        assert proxy_object.model.spec.httpsProxy == https_proxy

    def test_http_proxy(self, api_client, node_controler):
        proxy_url = env_variables['HTTP_PROXY']
        cluster = self.create_cluster(api_client)
        cluster_id = cluster.id
        cluster = api_client.set_cluster_proxy(cluster_id=cluster_id, http_proxy=proxy_url)

        assert cluster.http_proxy == proxy_url
        assert cluster.https_proxy == proxy_url
        self.generate_and_download_image(
            cluster_id=cluster_id, api_client=api_client
        )
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

        #Assert proxy is defined in install config
        self.is_proxy_defined_in_install_config(
            cluster_id=cluster_id,
            api_client=api_client,
            http_proxy=proxy_url,
            https_proxy=proxy_url
        )

        #Wait for cluster to install
        self.wait_untill_all_hosts_install(cluster_id=cluster_id, api_client=api_client)
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

        #Assert proxy value is defined in cluster wide proxy object
        self.are_proxy_paramas_defined_in_clusterwide_proxy(
            cluster_id=cluster_id,
            api_client=api_client,
            http_proxy=proxy_url,
            https_proxy=proxy_url
        )







