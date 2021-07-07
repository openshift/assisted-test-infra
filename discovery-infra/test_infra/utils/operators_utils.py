import os
from typing import List

import waiting
from assisted_service_client import MonitoredOperator
from logger import log

from test_infra import consts


def get_env(env, default=None):
    res = os.environ.get(env, "").strip()
    if not res or res == '""':
        res = default
    return res


def parse_olm_operators_from_env():
    return get_env("OLM_OPERATORS", default="").lower().split()


def _are_operators_in_status(
    operators: List[MonitoredOperator], operators_count: int, statuses: List[str], fall_on_error_status: bool
) -> bool:
    log.info(
        "Asked operators to be in one of the statuses from %s and currently operators statuses are %s",
        statuses,
        [(operator.name, operator.status, operator.status_info) for operator in operators],
    )

    if len([operator for operator in operators if operator.status in statuses]) >= operators_count:
        return True

    if fall_on_error_status:
        for operator in operators:
            if operator.status == consts.OperatorStatus.FAILED:
                raise ValueError(
                    f"Operator {operator.name} status is {consts.OperatorStatus.FAILED} "
                    f"with info {operator.status_info}"
                )

    return False


def is_operator_in_status(operators: List[MonitoredOperator], operator_name: str, status: str) -> bool:
    log.info(
        "Asked operator %s to be in status: %s, and currently operators statuses are %s",
        operator_name,
        status,
        [(operator.name, operator.status, operator.status_info) for operator in operators],
    )
    return any(operator.status == status for operator in operators if operator.name == operator_name)


def wait_till_all_operators_are_in_status(
    client,
    cluster_id,
    operators_count,
    operator_types,
    statuses,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
    fall_on_error_status=False,
    interval=5,
):
    log.info(f"Wait till {operators_count} {operator_types} operators are in one of the statuses {statuses}")

    try:
        waiting.wait(
            lambda: _are_operators_in_status(
                filter_operators_by_type(client.get_cluster_operators(cluster_id), operator_types),
                operators_count,
                statuses,
                fall_on_error_status,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Monitored {operator_types} operators to be in of the statuses {statuses}",
        )
    except BaseException:
        operators = client.get_cluster_operators(cluster_id)
        log.info("All operators: %s", operators)
        raise


def filter_operators_by_type(operators: List[MonitoredOperator], operator_types: List[str]) -> List[MonitoredOperator]:
    return list(filter(lambda operator: operator.operator_type in operator_types, operators))


def resource_param(base_value: int, resource_name: str, operator: str):
    try:
        value = base_value
        resource = consts.OperatorResource.values()[operator][resource_name]
        if value <= resource:
            value = value + resource
        return value
    except KeyError as e:
        raise ValueError(f"Unknown operator name {e.args[0]}")
