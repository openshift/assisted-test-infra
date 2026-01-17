from typing import List

import pytest
from _pytest.nodes import Item
from assisted_service_client.rest import ApiException

import consts
from assisted_test_infra.test_infra import utils
from service_client import log
from service_client.client_validator import verify_client_version
from tests.config import global_variables

assert global_variables.pull_secret is not None, "Missing pull secret"


@pytest.fixture(scope="session")
def api_client():
    log.info("--- SETUP --- api_client\n")
    client = None

    # prevent from kubeapi tests from failing if the fixture is dependant on api_client fixture
    if not global_variables.is_kube_api:
        log.debug("Getting new inventory client")
        try:
            verify_client_version()
            client = global_variables.get_api_client()
        except (RuntimeError, ApiException) as e:
            log.warning(f"Failed to access api client, {e}")

    yield client


def get_supported_operators() -> List[str]:
    try:
        return sorted(global_variables.get_api_client().get_supported_operators())
    except RuntimeError:
        return []  # if no service found return empty operator list


def get_supported_bundles() -> List[str]:
    try:
        bundles = global_variables.get_api_client().get_supported_bundles()
        return sorted([bundle.id for bundle in bundles if bundle.id])
    except RuntimeError:
        return []  # if no service found return empty bundle list


def get_available_openshift_versions() -> List[str]:
    try:
        openshift_versions = global_variables.get_api_client().get_openshift_versions()
    except RuntimeError:
        return [global_variables.openshift_version]  # if no service found return hard-coded version number

    available_versions = set(utils.get_major_minor_version(version) for version in openshift_versions.keys())
    override_version = utils.get_openshift_version(allow_default=False)

    if override_version:
        if override_version == consts.OpenshiftVersion.MULTI_VERSION.value:
            return sorted(list(available_versions), key=lambda s: list(map(int, s.split("."))))
        if override_version in available_versions:
            return [override_version]
        raise ValueError(
            f"Invalid version {override_version}, can't find among versions: "
            f"{list(available_versions) + [consts.OpenshiftVersion.MULTI_VERSION.value]}"
        )

    return [k for k, v in openshift_versions.items() if "default" in v and v["default"]]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Item, call):
    outcome = yield
    result = outcome.get_result()

    setattr(item, "result_" + result.when, result)


# -------------------- vSphere fixtures (shared) --------------------
import os  # noqa: E402  keep local to avoid leaking to import time before pytest collection
from consts import consts as _consts  # noqa: E402
from tests.config.global_configs import reset_global_variables  # noqa: E402


@pytest.fixture
def force_vsphere_platform():
    os.environ["TF_PLATFORM"] = _consts.Platforms.VSPHERE
    reset_global_variables()
    yield


@pytest.fixture
def vsphere_cluster_config(new_cluster_configuration):
    new_cluster_configuration.platform = _consts.Platforms.VSPHERE
    base_dns = os.getenv("VSPHERE_BASE_DNS_DOMAIN")
    if base_dns:
        new_cluster_configuration.base_dns_domain = base_dns
    lb_ip = os.getenv("VSPHERE_LB_IP")
    if lb_ip:
        new_cluster_configuration.api_vips = [{"ip": lb_ip}]
        new_cluster_configuration.ingress_vips = [{"ip": lb_ip}]
    return new_cluster_configuration


@pytest.fixture
def vsphere_controller_config(new_controller_configuration):
    cfg = new_controller_configuration
    # Map required vSphere variables from env (fallback to GOVC_* where applicable)
    cfg.vsphere_server = os.getenv("VSPHERE_VCENTER") or os.getenv("GOVC_URL")
    cfg.vsphere_username = os.getenv("VSPHERE_USERNAME") or os.getenv("GOVC_USERNAME")
    cfg.vsphere_password = os.getenv("VSPHERE_PASSWORD") or os.getenv("GOVC_PASSWORD")
    cfg.vsphere_datacenter = os.getenv("VSPHERE_DATACENTER") or os.getenv("GOVC_DATACENTER")
    cfg.vsphere_datastore = os.getenv("VSPHERE_DATASTORE") or os.getenv("GOVC_DATASTORE")
    # Defaults that are commonly used if not provided
    cfg.vsphere_network = os.getenv("VSPHERE_NETWORK") or "VM Network"
    cfg.vsphere_parent_folder = os.getenv("VSPHERE_PARENT_FOLDER") or "e2e-qe"
    cfg.vsphere_folder = os.getenv("VSPHERE_FOLDER") or ""
    cluster = os.getenv("VSPHERE_CLUSTER")
    if cluster:
        cfg.vsphere_cluster = cluster
    return cfg
