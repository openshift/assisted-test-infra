import pytest
import semver
from junit_report import JunitTestSuite
from kubernetes import client, config

import consts

from assisted_test_infra.test_infra.utils import console_redirect_decorator, wait_for_pod_ready

from tests.base_test import BaseTest
from tests.config import global_variables
from tests.conftest import get_available_openshift_versions, get_supported_operators


@console_redirect_decorator
class TestInstall(BaseTest):
    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_install(self, cluster, openshift_version):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed(fall_on_pending_status=True)

    @JunitTestSuite()
    @pytest.mark.parametrize("openshift_version", get_available_openshift_versions())
    def test_infra_env_install(self, infra_env, openshift_version):
        infra_env.prepare_for_installation()

    @JunitTestSuite()
    @pytest.mark.parametrize("network_type", [consts.NetworkType.OpenShiftSDN, consts.NetworkType.OVNKubernetes])
    def test_networking(self, cluster, network_type):
        if semver.compare(_get_semver(global_variables.openshift_version), "4.15.0") >= 0:
            raise ValueError(
                "parametrization of network type not necessary from 4.15.0 and above,"
                " as the only supported network type is OVN"
            )
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed(fall_on_pending_status=True)

    @JunitTestSuite()
    @pytest.mark.parametrize("olm_operators", get_supported_operators())
    def test_olm_operator(self, cluster, olm_operators):
        cluster.prepare_for_installation()
        cluster.start_install_and_wait_for_installed(fall_on_pending_status=True)

    @JunitTestSuite()
    def test_mce_storage_post(self):
        config.load_kube_config()

        # get agent service config
        asc_list = client.CustomObjectsApi().list_cluster_custom_object(
            group="agent-install.openshift.io", version="v1beta1", plural="agentserviceconfigs"
        )
        assert "items" in asc_list
        assert len(asc_list["items"]) == 1, "Expected to have only one agentserviceconfig resource"
        agent_service_config = asc_list["items"][0]

        # get storage classes
        storage_classes_list = client.StorageV1Api().list_storage_class()
        assert len(storage_classes_list.items) > 0, "Expected storage class list to have one item or more"
        storage_classes = [storage_class.metadata.name for storage_class in storage_classes_list.items]

        # each storage pvc should have an existing storage class
        storage_claims = ["databaseStorage", "filesystemStorage", "imageStorage"]
        for key in storage_claims:
            assert key in agent_service_config["spec"]
            assert (
                agent_service_config["spec"][key]["storageClassName"] in storage_classes
            ), f"Expected {key} to match existing storageclass"

        v1 = client.CoreV1Api()
        mce_namespace = "multicluster-engine"
        # pvc should be bound
        pvcs = v1.list_namespaced_persistent_volume_claim(mce_namespace)
        for pvc in pvcs.items:
            assert pvc.status is not None, "Expected pod status"
            assert pvc.status.phase == "Bound", "Expected pvc to be bound"

        # workloads should be running
        selectors = ["app=assisted-service", "app=assisted-image-service"]
        for selector in selectors:
            wait_for_pod_ready(mce_namespace, selector)
            pods = v1.list_namespaced_pod(mce_namespace, label_selector=selector)
            assert len(pods.items) > 0, f"Expected to find one ore more pods with selector {selector}"
            pod = pods.items[0]
            for status in pod.status.container_statuses:
                assert status.ready, "Expected pod to be ready"
                assert status.started, "Expected pod to be started"
                assert status.state.running is not None, "Expected pod to be running"


def _get_semver(version: str) -> str:
    """
    Ensure version to be semver compatible
    """
    if version.count(".") > 1:
        return version
    return _get_semver(f"{version}.0")
