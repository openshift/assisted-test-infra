import logging
from typing import List

import pytest
from test_infra import utils
from test_infra.assisted_service_api import ClientFactory, InventoryClient
from tests.config import global_variables


@pytest.fixture(scope="session")
def api_client():
    logging.info('--- SETUP --- api_client\n')
    yield get_api_client()


def get_api_client(offline_token=None, **kwargs) -> InventoryClient:
    url = global_variables.remote_service_url
    offline_token = offline_token or global_variables.offline_token

    if not url:
        url = utils.get_local_assisted_service_url(
            global_variables.namespace, 'assisted-service', utils.get_env('DEPLOY_TARGET'))

    return ClientFactory.create_client(url, offline_token, **kwargs)


def get_available_openshift_versions() -> List[str]:
    available_versions = list(get_api_client().get_openshift_versions().keys())
    specific_version = utils.get_openshift_version(default=None)
    if specific_version:
        if specific_version in available_versions:
            return [specific_version]
        raise ValueError(f"Invalid version {specific_version}, can't find among versions: {available_versions}")

    return sorted(available_versions)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()

    setattr(item, "result_" + result.when, result)
