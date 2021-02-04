import pytest
from tests.base_test import BaseTest
from tests.conftest import get_api_client
from tests.conftest import env_variables
import oc_utils


class TestInstall(BaseTest):
    @pytest.mark.parametrize(
        "openshift_version", list(get_api_client().get_openshift_versions().keys())
    )
    def test_install(self, nodes, cluster, openshift_version):
        # Define new cluster
        new_cluster = cluster(openshift_version=openshift_version)
        new_cluster.prepare_for_install(nodes=nodes)
        # Install Cluster
        new_cluster.start_install_and_wait_for_installed()

        # Check that metal3 is enabled for versions > 4.6
        major, minor = openshift_version.split(".")
        if (int(major) == 4 and int(minor) > 6) or int(major) > 4:
            print("testing 4.7+ metal3 enablement")
            new_cluster.download_kubeconfig(env_variables["kubeconfig_path"])
            print("got kubeconfig")
            oc_utils.check_metal3(env_variables["kubeconfig_path"])
