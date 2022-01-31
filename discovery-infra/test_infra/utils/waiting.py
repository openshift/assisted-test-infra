from typing import List

import waiting

from logger import log
from test_infra import consts as consts
from test_infra.utils import are_host_progress_in_stage


def _get_cluster_hosts_with_mac(client, cluster_id, macs):
    return [client.get_host_by_mac(cluster_id, mac) for mac in macs]


def _are_hosts_in_status(hosts, nodes_count, statuses, status_info="", fall_on_error_status=True):
    hosts_in_status = [host for host in hosts if (host["status"] in statuses and
                                                  host["status_info"].startswith(status_info))]
    if len(hosts_in_status) >= nodes_count:
        return True
    elif fall_on_error_status and len([host for host in hosts if host["status"] == consts.NodesStatus.ERROR]) > 0:
        hosts_in_error = [
            (i, host["id"], host["requested_hostname"], host["role"], host["status"], host["status_info"])
            for i, host in enumerate(hosts, start=1)
            if host["status"] == consts.NodesStatus.ERROR
        ]
        log.error("Some of the hosts are in insufficient or error status. Hosts in error %s", hosts_in_error)
        raise Exception("All the nodes must be in valid status, but got some in error")

    log.info(
        "Asked hosts to be in one of the statuses from %s and currently hosts statuses are %s",
        statuses,
        [
            (i, host["id"], host.get("requested_hostname"), host.get("role"), host["status"], host["status_info"])
            for i, host in enumerate(hosts, start=1)
        ],
    )
    return False


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
        waiting_for="Nodes to be in of the statuses %s" % statuses,
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
):
    log.info("Wait till %s nodes are in one of the statuses %s", nodes_count, statuses)

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=client.get_cluster_hosts(cluster_id),
            nodes_count=nodes_count,
            statuses=statuses,
            status_info=status_info,
            fall_on_error_status=fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Nodes to be in of the statuses %s" % statuses,
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
        waiting_for="Nodes to be in of the statuses %s" % statuses,
    )


def wait_till_at_least_one_host_is_in_status(
        client,
        cluster_id,
        statuses,
        status_info="",
        nodes_count=1,
        timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
        fall_on_error_status=True,
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
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Node to be in of the statuses %s" % statuses,
    )


def wait_till_specific_host_is_in_status(
        client,
        cluster_id,
        host_name,
        nodes_count,
        statuses,
        timeout=consts.NODES_REGISTERED_TIMEOUT,
        fall_on_error_status=True,
        interval=consts.DEFAULT_CHECK_STATUSES_INTERVAL,
):
    log.info(f"Wait till {nodes_count} host is in one of the statuses: {statuses}")

    waiting.wait(
        lambda: _are_hosts_in_status(
            hosts=[client.get_host_by_name(cluster_id, host_name)],
            nodes_count=nodes_count,
            statuses=statuses,
            fall_on_error_status=fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Node to be in of the statuses %s" % statuses,
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
            lambda: are_host_progress_in_stage(
                client.get_cluster_hosts(cluster_id),
                stages,
                nodes_count,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Node to be in of the stage %s" % stages,
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
            lambda: are_host_progress_in_stage(
                [client.get_host_by_name(cluster_id, host_name)],
                stages,
                nodes_count,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Node to be in of the stage %s" % stages,
        )
    except BaseException:
        hosts = [client.get_host_by_name(cluster_id, host_name)]
        log.error(
            f"All nodes stages: "
            f"{[host['progress']['current_stage'] for host in hosts]} "
            f"when waited for {stages}"
        )
        raise
