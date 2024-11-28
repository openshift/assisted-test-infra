import os
from typing import List

import waiting
from assisted_service_client import MonitoredOperator

import consts
from service_client import InventoryClient, log


def get_env(env, default=None):
    res = os.environ.get(env, "").strip()
    if not res or res == '""':
        res = default
    return res


def _are_operators_in_status(
    cluster_id: str,
    client: InventoryClient,
    operators: List[MonitoredOperator],
    operators_count: int,
    statuses: List[str],
    fall_on_error_status: bool,
) -> bool:
    log.info(
        "Asked operators to be in one of the statuses from %s and currently operators statuses are %s",
        statuses,
        [(operator.name, operator.status, operator.status_info) for operator in operators],
    )

    if fall_on_error_status:
        for operator in operators:
            if operator.status == consts.OperatorStatus.FAILED:
                _Exception = consts.olm_operators.get_exception_factory(operator.name)  # noqa: N806
                raise _Exception(f"Operator {operator.name} status is failed with info {operator.status_info}")

    cluster = client.cluster_get(cluster_id=cluster_id).to_dict()
    log.info("Cluster %s progress info: %s", cluster_id, cluster["progress"])
    if len([operator for operator in operators if operator.status in statuses]) >= operators_count:
        return True

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
    interval=10,
):
    log.info(f"Wait till {operators_count} {operator_types} operators are in one of the statuses {statuses}")

    try:
        waiting.wait(
            lambda: _are_operators_in_status(
                cluster_id,
                client,
                filter_operators_by_type(client.get_cluster_operators(cluster_id), operator_types),
                operators_count,
                statuses,
                fall_on_error_status,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Monitored {operator_types} operators to be in of the statuses {statuses}",
        )
    except BaseException as e:
        operators = client.get_cluster_operators(cluster_id)
        invalid_operators = [o.name for o in operators if o.status != consts.OperatorStatus.AVAILABLE]
        log.error("Several cluster operators are not available. All operator statuses: %s", operators)
        e.add_note(f"Failed to deploy the following operators {invalid_operators}")
        raise


def filter_operators_by_type(operators: List[MonitoredOperator], operator_types: List[str]) -> List[MonitoredOperator]:
    log.info(f"Attempting to filter operators by {operator_types} types, available operates {operators}")
    return list(filter(lambda operator: operator.operator_type in operator_types, operators))


def resource_param(base_value: int, resource_name: str, operator: str, is_sno: bool = False):
    try:
        resource = consts.OperatorResource.values(is_sno)[operator][resource_name]
        return max(base_value, resource)
    except KeyError as e:
        raise ValueError(f"Unknown operator name {e.args[0]}") from e
