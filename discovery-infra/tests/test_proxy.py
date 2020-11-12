import pytest
import openshift as oc
from logger import log

from tests.base_test import BaseTest
from tests.conftest import env_variables


@pytest.mark.skipif(not env_variables['http_proxy_url'], reason="no proxy environment")
class TestProxy(BaseTest):
    def _is_proxy_defined_in_install_config(self, cluster, http_proxy, https_proxy):
        install_config = cluster.get_install_config()
        log.info(f'Verifying proxy parameters are deinfied in install-config.yaml for cluster {cluster.id}')
        assert install_config['proxy']['httpProxy'] == http_proxy
        assert install_config['proxy']['httpsProxy'] == https_proxy

    def _are_proxy_paramas_defined_in_clusterwide_proxy(self, cluster, http_proxy, https_proxy):
        cluster.download_kubeconfig()
        log.info(f'Verifying proxy parameters are deinfied in cluster wide proxy object for Cluster {cluster.id}')
        proxy_object = oc.selector('proxy/cluster').objects()[0]
        assert proxy_object.model.spec.httpProxy == http_proxy
        assert proxy_object.model.spec.httpsProxy == https_proxy


    @pytest.mark.parametrize(
        "http_proxy, https_proxy", 
        [
            (env_variables['http_proxy_url'], ""), 
            (env_variables['http_proxy_url'], env_variables['https_proxy_url'])
        ]
    )
    @pytest.mark.proxy
    def test_http_proxy(self, nodes, cluster, http_proxy, https_proxy):
        expected_http_proxy_value = http_proxy
        expected_https_proxy_value = https_proxy if https_proxy else http_proxy
        #Define new cluster
        new_cluster = cluster(env_variables['cluster_name'])
        #Set cluster proxy details
        new_cluster.set_proxy_values(http_proxy, https_proxy)
        cluster_details = new_cluster.get_details()
        #Test proxy params are set 
        assert cluster_details.http_proxy == expected_http_proxy_value
        assert cluster_details.https_proxy == expected_https_proxy_value
        new_cluster.prepare_for_install(nodes)
        #Start Cluster Install
        new_cluster.start_install_and_wait_for_installed()

        #Assert proxy is defined in install config
        self._is_proxy_defined_in_install_config(
            cluster=new_cluster,
            http_proxy=expected_http_proxy_value,
            https_proxy=expected_https_proxy_value
        )

        #Assert proxy value is defined in cluster wide proxy object
        self._are_proxy_paramas_defined_in_clusterwide_proxy(
            cluster=new_cluster,
            http_proxy=expected_http_proxy_value,
            https_proxy=expected_https_proxy_value
        )