import os
import pytest
import openshift as oc
import logging

from tests.base_test import BaseTest
from tests.conftest import env_variables
from test_infra.controllers.proxy_controller.proxy_controller import ProxyController

class TestProxy(BaseTest):
    @pytest.fixture()
    def proxy_server(self):
        logging.info('--- SETUP --- proxy controller')
        proxy_servers = []

        def start_proxy_server(**kwargs):
            proxy_server = ProxyController(**kwargs)
            proxy_servers.append(proxy_server)

            return proxy_server

        yield start_proxy_server
        logging.info('--- TEARDOWN --- proxy controller')
        for server in proxy_servers:
            server.remove()

    def _is_proxy_defined_in_install_config(self, cluster, http_proxy, https_proxy):
        install_config = cluster.get_install_config()
        logging.info(f'Verifying proxy parameters are deinfied in install-config.yaml for cluster {cluster.id}')
        assert install_config['proxy']['httpProxy'] == http_proxy
        assert install_config['proxy']['httpsProxy'] == https_proxy

    def _are_proxy_paramas_defined_in_clusterwide_proxy(self, cluster, http_proxy, https_proxy):
        cluster.download_kubeconfig()
        logging.info(f'Verifying proxy parameters are deinfied in cluster wide proxy object for Cluster {cluster.id}')
        proxy_object = oc.selector('proxy/cluster').objects()[0]
        assert proxy_object.model.spec.httpProxy == http_proxy
        assert proxy_object.model.spec.httpsProxy == https_proxy


    @pytest.mark.parametrize(
        "http_proxy_params, https_proxy_params",
        [
            ({'name': 'squid_auth', 'port': 3128, 'authenticated': True} , {}),
            ({'name': 'squid_http', 'port': 3128, 'denied_port': 443} , {'name': 'squid_https', 'port': 3130, 'denied_port': 80}),
            ({'name': 'squid_http', 'port': 3128} , {})
        ]
    )
    @pytest.mark.regression
    def test_http_proxy(self, nodes, cluster, proxy_server, http_proxy_params, https_proxy_params):
        http_server = proxy_server(**http_proxy_params)
        https_server = proxy_server(**https_proxy_params)
        http_proxy_url = http_server.address
        https_proxy_url = https_server.address
        expected_http_proxy_value = http_proxy_url
        expected_https_proxy_value = https_proxy_url if https_proxy_url else http_proxy_url
        # Define new cluster
        new_cluster = cluster(env_variables['cluster_name'])
        # Set cluster proxy details
        new_cluster.set_proxy_values(http_proxy_url, https_proxy_url)
        cluster_details = new_cluster.get_details()
        # Test proxy params are set 
        assert cluster_details.http_proxy == expected_http_proxy_value
        assert cluster_details.https_proxy == expected_https_proxy_value
        new_cluster.prepare_for_install(nodes)
        # Start Cluster Install
        new_cluster.start_install_and_wait_for_installed()

        # Assert proxy is defined in install config
        self._is_proxy_defined_in_install_config(
            cluster=new_cluster,
            http_proxy=expected_http_proxy_value,
            https_proxy=expected_https_proxy_value
        )

        # Assert proxy value is defined in cluster wide proxy object
        self._are_proxy_paramas_defined_in_clusterwide_proxy(
            cluster=new_cluster,
            http_proxy=expected_http_proxy_value,
            https_proxy=expected_https_proxy_value
        )