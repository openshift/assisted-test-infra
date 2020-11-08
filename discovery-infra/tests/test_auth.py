import pytest
from contextlib import suppress
from typing import Optional
from tests.base_test import BaseTest
from tests.conftest import env_variables, get_api_client
from assisted_service_client.rest import ApiException
from test_infra import utils
from test_infra.helper_classes.cluster import Cluster

SECOND_OFFLINE_TOKEN = utils.get_env('SECOND_OFFLINE_TOKEN')
SECOND_PULL_SECRET = utils.get_env('SECOND_PULL_SECRET')


@pytest.fixture()
def api_client():
    yield get_api_client


@pytest.mark.skipif(not env_variables['offline_token'], reason="not cloud env")
class TestAuth(BaseTest):
    @pytest.fixture()
    def cluster(self):
        clusters = []

        def get_cluster_func(api_client, cluster_name: Optional[str] = None, cluster_id: Optional[str] = None):
            res = Cluster(api_client=api_client, cluster_name=cluster_name, cluster_id=cluster_id)
            clusters.append(res)
            return res

        yield get_cluster_func

        for cluster in clusters:
            with suppress(ApiException):
                cluster.delete()

    def _send_dummy_step_result(self, cluster, host_id):
        cluster.host_post_step_result(
            host_id,
            step_type="inventory",
            step_id="inventory-e048e0db",
            exit_code=0,
            output="null"
        )

    def _update_dummy_install_progress(self, cluster, host_id):
        cluster.host_update_install_progress(host_id, "Failed")

    @pytest.mark.regression
    def test_user_authorization_negative(self, api_client, nodes, cluster):
        client_user1 = api_client()
        client_user2 = api_client(offline_token=SECOND_OFFLINE_TOKEN)

        cluster_client_user1 = cluster(client_user1, cluster_name=env_variables['cluster_name'])
        cluster_client_user2 = cluster(client_user2, cluster_id=cluster_client_user1.id)

        # user2 cannot get user1's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.get_details,
            status=404,
            reason="Not Found"
        )

        # user2 cannot delete user1's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.delete,
            status=404,
            reason="Not Found",
        )

        # user2 cannot generate ISO user1's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.generate_and_download_image,
            status=404,
            reason="Not Found"
        )

        cluster_client_user1.prepare_for_install(nodes=nodes)

        # user2 cannot patch user1's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.set_network_params,
            status=404,
            reason="Not Found",
            controller=nodes.controller
        )

        # user2 cannot list user2's hosts
        self.assert_http_error_code(
            api_call=cluster_client_user2.get_hosts,
            status=404,
            reason="Not Found",
        )

        # user2 cannot trigger user2's cluster install
        self.assert_http_error_code(
            api_call=cluster_client_user2.start_install,
            status=404,
            reason="Not Found"
        )

        # start cluster install
        cluster_client_user1.start_install()

        # user2 cannot download files from user2's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.download_kubeconfig_no_ingress,
            status=404,
            reason="Not Found",
        )

        # user2 cannot get user2's cluster install config
        self.assert_http_error_code(
            api_call=cluster_client_user2.get_install_config,
            status=404,
            reason="Not Found"
        )

        # user2 cannot cancel user2's cluster install
        self.assert_http_error_code(
            api_call=cluster_client_user2.cancel_install,
            status=404,
            reason="Not Found",
        )

        cluster_client_user1.wait_for_nodes_to_install()
        cluster_client_user1.wait_for_install()

        # user2 cannot get user2's cluster credentials
        self.assert_http_error_code(
            api_call=cluster_client_user2.get_admin_credentials,
            status=404,
            reason="Not Found"
        )

    @pytest.mark.regression
    def test_agent_authorization_negative(self, api_client, nodes, cluster):
        client_user1 = api_client()
        client_user2 = api_client(
            offline_token='',
            pull_secret=SECOND_PULL_SECRET,
            wait_for_api=False
        )

        cluster_client_user1 = cluster(client_user1, cluster_name=env_variables['cluster_name'])
        cluster_client_user2 = cluster(client_user2, cluster_id=cluster_client_user1.id)

        # agent with user2 pull secret cannot get user1's cluster details
        self.assert_http_error_code(
            api_call=cluster_client_user2.get_details,
            status=404,
            reason="Not Found",
        )

        # agent with user2 pull secret cannot register to user1's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.register_dummy_host,
            status=404,
            reason="Not Found",
        )

        cluster_client_user1.prepare_for_install(nodes=nodes)

        # agent with user2 pull secret cannot list cluster hosts
        self.assert_http_error_code(
            api_call=cluster_client_user2.get_hosts,
            status=404,
            reason="Not Found",
        )

        host_ids = cluster_client_user1.get_host_ids()

        # agent with user2 pull secret cannot get next step
        self.assert_http_error_code(
            api_call=cluster_client_user2.host_get_next_step,
            status=404,
            reason="Not Found",
            host_id=host_ids[0]
        )

        # agent with user2 pull secret cannot update on next step
        self.assert_http_error_code(
            api_call=self._send_dummy_step_result,
            status=404,
            reason="Not Found",
            cluster=cluster_client_user2,
            host_id=host_ids[0]
        )

        cluster_client_user1.start_install()

        # agent with user2 pull secret cannot update install progress
        self.assert_http_error_code(
            api_call=self._update_dummy_install_progress,
            status=404,
            reason="Not Found",
            cluster=cluster_client_user2,
            host_id=host_ids[0]
        )

        # user2 cannot download files from user2's cluster
        self.assert_http_error_code(
            api_call=cluster_client_user2.download_kubeconfig_no_ingress,
            status=404,
            reason="Not Found",
        )

        cluster_client_user1.wait_for_nodes_to_install()

        # agent with user2 pull secret cannot complete installation
        self.assert_http_error_code(
            api_call=cluster_client_user2.host_complete_install,
            status=404,
            reason="Not Found",
        )
