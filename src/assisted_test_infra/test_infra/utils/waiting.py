from typing import Any, Dict, List, Tuple

import waiting

import consts
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.exceptions import InstallationFailedError, InstallationPendingActionError
from service_client import log


def _get_cluster_hosts_with_mac(client, cluster_id, macs):
    return [client.get_host_by_mac(cluster_id, mac) for mac in macs]


def _are_hosts_in_status(
    hosts, nodes_count, statuses, status_info="", fall_on_error_status=True, fall_on_pending_status=False
):
    hosts_in_status = [
        host for host in hosts if (host["status"] in statuses and host["status_info"].startswith(status_info))
    ]
    if len(hosts_in_status) >= nodes_count:
        return True

    if fall_on_error_status and len([host for host in hosts if host["status"] == consts.NodesStatus.ERROR]) > 0:
        hosts_in_error = [
            (i, host["id"], host["requested_hostname"], host["role"], host["status"], host["status_info"])
            for i, host in enumerate(hosts, start=1)
            if host["status"] == consts.NodesStatus.ERROR
        ]
        log.error("Some of the hosts are in insufficient or error status. Hosts in error %s", hosts_in_error)
        raise InstallationFailedError()

    if fall_on_pending_status and len([host for host in hosts if "pending" in host["status"]]) > 0:
        hosts_in_pending = [
            (i, host["id"], host["requested_hostname"], host["role"], host["status"], host["status_info"])
            for i, host in enumerate(hosts, start=1)
            if "pending" in host["status"]
        ]
        log.error("Some of the hosts are in pending user action. Hosts pending %s", hosts_in_pending)
        raise InstallationPendingActionError()

    log.info(
        "Asked hosts to be in one of the statuses from %s %s and currently hosts statuses are %s",
        statuses,
        status_info,
        host_statuses(hosts),
    )
    return False


def _are_hosts_using_agent_image(hosts: List[Dict[str, Any]], image: str) -> bool:
    for host in hosts:
        if host.get("discovery_agent_version") != image:
            return False
    return True


def host_statuses(hosts) -> List[Tuple[int, str, str, str, str, str]]:
    return [
        (i, host["id"], host.get("requested_hostname"), host.get("role"), host["status"], host["status_info"])
        for i, host in enumerate(hosts, start=1)
    ]


def wait_till_hosts_with_macs_are_in_status(
    client,
    cluster_id,
    macs,
    statuses,
    timeout=consts.NODES_REGISTERED_TIMEOUT,
    fall_on_error_status=True,
    interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
):
    log.info("Wait till %s nodes are in one of the statuses %s", len(macs), statuses)

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=_get_cluster_hosts_with_mac(client, cluster_id, macs),
            nodes_count=len(macs),
            statuses=statuses,
            fall_on_error_status=fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for=f"Nodes to be in of the statuses {statuses}",
    )


def wait_till_all_hosts_are_in_status(
    client,
    cluster_id,
    nodes_count,
    statuses,
    status_info="",
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
    fall_on_error_status=True,
    interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
    fall_on_pending_status=False,
):
    log.info("Wait till %s nodes are in one of the statuses %s", nodes_count, statuses)

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=client.get_cluster_hosts(cluster_id),
            nodes_count=nodes_count,
            statuses=statuses,
            status_info=status_info,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for=f"Nodes to be in of the statuses {statuses}",
    )


def wait_till_all_hosts_use_agent_image(
    client: Any,
    cluster_id: str,
    image: str,
    timeout: int = consts.NODES_REGISTERED_TIMEOUT,
    interval: int = consts.DEFAULT_CHECK_STATUSES_INTERVAL,
) -> None:
    log.info("Wait till all nodes are using agent image %s", image)

    waiting.wait(
        lambda: _are_hosts_using_agent_image(
            hosts=client.get_cluster_hosts(cluster_id),
            image=image,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for=f"Nodes to be using agent image {image}",
    )


def wait_till_all_infra_env_hosts_are_in_status(
    client,
    infra_env_id,
    nodes_count,
    statuses,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
    fall_on_error_status=True,
    interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
):
    log.info("Wait till %s nodes are in one of the statuses %s", nodes_count, statuses)

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=client.get_infra_env_hosts(infra_env_id),
            nodes_count=nodes_count,
            statuses=statuses,
            fall_on_error_status=fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for=f"Nodes to be in of the statuses {statuses}",
    )


def wait_till_at_least_one_host_is_in_status(
    client,
    cluster_id,
    statuses,
    status_info="",
    nodes_count=1,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
    fall_on_error_status=True,
    fall_on_pending_status=False,
    interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
):
    log.info("Wait till 1 node is in one of the statuses %s", statuses)

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=client.get_cluster_hosts(cluster_id),
            nodes_count=nodes_count,
            statuses=statuses,
            status_info=status_info,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for=f"Node to be in of the statuses {statuses}",
    )


def wait_till_specific_host_is_in_status(
    client,
    cluster_id,
    host_name,
    nodes_count,
    statuses,
    status_info="",
    timeout=consts.NODES_REGISTERED_TIMEOUT,
    fall_on_error_status=True,
    interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
):
    log.info(f"Wait till {nodes_count} host is in one of the statuses: {statuses} {status_info}")

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=[client.get_host_by_name(cluster_id, host_name)],
            nodes_count=nodes_count,
            statuses=statuses,
            status_info=status_info,
            fall_on_error_status=fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for=f"Node to be in of the statuses {statuses}",
    )


def wait_till_at_least_one_host_is_in_stage(
    client,
    cluster_id,
    stages,
    nodes_count=1,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT / 2,
    interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
):
    log.info(f"Wait till {nodes_count} node is in stage {stages}")
    try:
        waiting.wait(
            lambda: utils.are_host_progress_in_stage(
                client.get_cluster_hosts(cluster_id),
                stages,
                nodes_count,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Node to be in of the stage {stages}",
        )
    except BaseException:
        hosts = client.get_cluster_hosts(cluster_id)
        log.error(
            f"All nodes stages: "
            f"{[host['progress']['current_stage'] for host in hosts]} "
            f"when waited for {stages}"
        )
        raise


def wait_till_specific_host_is_in_stage(
    client,
    cluster_id: str,
    host_name: str,
    stages: List[str],
    nodes_count: int = 1,
    timeout: int = consts.CLUSTER_INSTALLATION_TIMEOUT / 2,
    interval: int = 5,
):
    log.info(f"Wait till {host_name} host is in stage {stages}")
    try:
        waiting.wait(
            lambda: utils.are_host_progress_in_stage(
                [client.get_host_by_name(cluster_id, host_name)],
                stages,
                nodes_count,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Node to be in of the stage {stages}",
        )
    except BaseException:
        hosts = [client.get_host_by_name(cluster_id, host_name)]
        log.error(
            f"All nodes stages: "
            f"{[host['progress']['current_stage'] for host in hosts]} "
            f"when waited for {stages}"
        )
        raise


def wait_till_cluster_is_in_status(
    client,
    cluster_id,
    statuses: List[str],
    timeout=consts.NODES_REGISTERED_TIMEOUT,
    interval=30,
    break_statuses: List[str] = None,
):
    log.info("Wait till cluster %s is in status %s", cluster_id, statuses)
    try:
        if break_statuses:
            statuses += break_statuses
        waiting.wait(
            lambda: utils.is_cluster_in_status(client=client, cluster_id=cluster_id, statuses=statuses),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for=f"Cluster to be in status {statuses}",
        )
        if break_statuses and utils.is_cluster_in_status(client, cluster_id, break_statuses):
            raise BaseException(
                f"Stop installation process, " f"cluster is in status {client.cluster_get(cluster_id).status}"
            )
    except BaseException:
        log.error("Cluster status is: %s", client.cluster_get(cluster_id).status)
        log.error("Hosts statuses are: %s", host_statuses(client.get_cluster_hosts(cluster_id)))
        raise
