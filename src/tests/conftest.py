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


def get_available_openshift_versions() -> List[str]:
    openshift_versions = global_variables.get_api_client().get_openshift_versions()
    default_version = [k for k, v in openshift_versions.items() if "default" in v and v["default"]].pop()
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

    return [default_version]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Item, call):
    outcome = yield
    result = outcome.get_result()

    setattr(item, "result_" + result.when, result)
