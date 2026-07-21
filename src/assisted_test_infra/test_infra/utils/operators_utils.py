import json
import os
from typing import List, Optional

import waiting
from assisted_service_client import MonitoredOperator
from kubernetes.client import ApiException, CustomObjectsApi

import consts
from service_client import ClientFactory, InventoryClient, log

NETWORK_OBSERVABILITY_FLOWCOLLECTOR_GROUP = "flows.netobserv.io"
NETWORK_OBSERVABILITY_FLOWCOLLECTOR_VERSION = "v1beta2"
NETWORK_OBSERVABILITY_FLOWCOLLECTOR_PLURAL = "flowcollectors"
NETWORK_OBSERVABILITY_FLOWCOLLECTOR_NAME = "cluster"
NETWORK_OBSERVABILITY_FLOWCOLLECTOR_NAMESPACE = "netobserv"


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
        value = base_value
        resource = consts.OperatorResource.values(is_sno)[operator][resource_name]
        if value <= resource:
            value = value + resource
        return value
    except KeyError as e:
        raise ValueError(f"Unknown operator name {e.args[0]}") from e


def verify_network_observability_properties(
    operators: List[MonitoredOperator],
    expected_sampling: int = consts.olm_operators.NETWORK_OBSERVABILITY_E2E_SAMPLING,
    expect_flow_collector: bool = consts.olm_operators.NETWORK_OBSERVABILITY_E2E_CREATE_FLOW_COLLECTOR,
) -> None:
    operator = next((op for op in operators if op.name == consts.OperatorType.NETWORK_OBSERVABILITY), None)
    if operator is None:
        raise AssertionError("network-observability monitored operator not found on cluster")

    try:
        properties = json.loads(operator.properties or "{}")
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid network-observability properties: {operator.properties}") from exc

    if properties.get("createFlowCollector") is not expect_flow_collector:
        raise AssertionError(
            f"expected createFlowCollector={expect_flow_collector}, got {properties.get('createFlowCollector')}"
        )
    if properties.get("sampling") != expected_sampling:
        raise AssertionError(f"expected sampling={expected_sampling}, got {properties.get('sampling')}")

    log.info(
        "Verified network-observability properties on monitored operator: createFlowCollector=%s sampling=%s",
        expect_flow_collector,
        expected_sampling,
    )


def _get_flow_collector(kubeconfig_path: str) -> dict:
    api = CustomObjectsApi(ClientFactory.create_kube_api_client(kubeconfig_path))
    try:
        return api.get_cluster_custom_object(
            group=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_GROUP,
            version=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_VERSION,
            plural=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_PLURAL,
            name=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_NAME,
        )
    except ApiException as cluster_scoped_error:
        if cluster_scoped_error.status not in (404, 403):
            raise
        # Template includes a namespace; support namespaced installs as a fallback.
        return api.get_namespaced_custom_object(
            group=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_GROUP,
            version=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_VERSION,
            namespace=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_NAMESPACE,
            plural=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_PLURAL,
            name=NETWORK_OBSERVABILITY_FLOWCOLLECTOR_NAME,
        )


def verify_network_observability_flow_collector(
    kubeconfig_path: str,
    expected_sampling: int = consts.olm_operators.NETWORK_OBSERVABILITY_E2E_SAMPLING,
    timeout: int = consts.CLUSTER_INSTALLATION_TIMEOUT,
) -> None:
    def _flow_collector_ready() -> bool:
        try:
            flow_collector = _get_flow_collector(kubeconfig_path)
        except Exception as exc:  # noqa: BLE001 - wait until CR exists / is readable
            log.info("Waiting for FlowCollector: %s", exc)
            return False

        sampling = flow_collector.get("spec", {}).get("agent", {}).get("ebpf", {}).get("sampling")
        log.info("FlowCollector sampling=%s (expected %s)", sampling, expected_sampling)
        return sampling == expected_sampling

    log.info("Waiting for FlowCollector cluster with sampling=%s", expected_sampling)
    waiting.wait(
        _flow_collector_ready,
        timeout_seconds=timeout,
        sleep_seconds=15,
        waiting_for=f"FlowCollector with sampling={expected_sampling}",
    )
    log.info("Verified FlowCollector sampling=%s on spoke cluster", expected_sampling)


def verify_network_observability_if_enabled(
    operators: List[MonitoredOperator],
    olm_operators: Optional[List],
    kubeconfig_path: str,
) -> None:
    configured = olm_operators or []
    names = [op if isinstance(op, str) else op.get("name") for op in configured]
    if consts.OperatorType.NETWORK_OBSERVABILITY not in names:
        return

    verify_network_observability_properties(operators)
    verify_network_observability_flow_collector(kubeconfig_path)