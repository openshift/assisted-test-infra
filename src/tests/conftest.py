from typing import List

import pytest
from _pytest.nodes import Item

import consts
from assisted_test_infra.test_infra import utils
from service_client import log
from tests.config import global_variables


@pytest.fixture(scope="session")
def api_client():
    log.info("--- SETUP --- api_client\n")
    yield global_variables.get_api_client()


def get_supported_operators() -> List[str]:
    try:
        return sorted(global_variables.get_api_client().get_supported_operators())
    except RuntimeError:
        return []  # if no service found return empty operator list


def get_available_openshift_versions() -> List[str]:
    try:
        openshift_versions = global_variables.get_api_client().get_openshift_versions()
    except RuntimeError:
        return [global_variables.openshift_version]  # if no service found return hard-coded version number

    available_versions = list(openshift_versions.keys())
    override_version = utils.get_openshift_version(allow_default=False)

    if override_version:
        if override_version == consts.OpenshiftVersion.MULTI_VERSION.value:
            return sorted(available_versions, key=lambda s: list(map(int, s.split("."))))
        if override_version in available_versions:
            return [override_version]
        raise ValueError(
            f"Invalid version {override_version}, can't find among versions: "
            f"{available_versions + [consts.OpenshiftVersion.MULTI_VERSION.value]}"
        )

    return [k for k, v in openshift_versions.items() if "default" in v and v["default"]]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Item, call):
    outcome = yield
    result = outcome.get_result()

    setattr(item, "result_" + result.when, result)
