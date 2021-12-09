import logging
from typing import List

import pytest
from _pytest.nodes import Item
from test_infra import utils
from tests.config import global_variables


@pytest.fixture(scope="session")
def api_client():
    logging.info("--- SETUP --- api_client\n")
    yield global_variables.get_api_client()


def get_available_openshift_versions() -> List[str]:
    available_versions = list(global_variables.get_api_client().get_openshift_versions().keys())
    override_version = utils.get_openshift_version(allow_default=False)

    if override_version:
        if override_version in available_versions:
            return [override_version]
        raise ValueError(f"Invalid version {override_version}, can't find among versions: {available_versions}")

    return sorted(available_versions)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Item, call):
    outcome = yield
    result = outcome.get_result()

    setattr(item, "result_" + result.when, result)
