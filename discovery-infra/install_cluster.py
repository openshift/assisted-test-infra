#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse

import bm_inventory_api
import consts
import utils
import waiting
from logger import log


# Verify folder to download kubeconfig exists. If will be needed in other places move to utils
def _verify_kube_download_folder(kubeconfig_path):
    if not utils.folder_exists(kubeconfig_path):
        exit(1)


def verify_pull_secret(cluster, client, pull_secret):
    if not cluster.pull_secret_set and not pull_secret:
        raise Exception("Can't install cluster %s, no pull secret was set" % cluster.id)
    if not cluster.pull_secret_set and pull_secret:
        cluster.pull_secret = pull_secret
        client.update_cluster(cluster.id, cluster)


def _install_cluster(client, cluster):
    cluster = client.install_cluster(cluster_id=cluster.id)
    utils.wait_till_cluster_is_in_status(
        client=client,
        cluster_id=cluster.id,
        timeout=consts.START_CLUSTER_INSTALLATION_TIMEOUT,
        statuses=[consts.ClusterStatus.INSTALLING],
    )
    utils.wait_till_all_hosts_are_in_status(
        client=client,
        cluster_id=cluster.id,
        nodes_count=len(cluster.hosts),
        statuses=[consts.NodesStatus.INSTALLING],
        interval=30,
    )


def wait_till_installed(client, cluster, timeout=60 * 60 * 2):
    log.info("Waiting %s till cluster finished installation", timeout)
    # TODO: Change host validation for only previous known hosts
    utils.wait_till_all_hosts_are_in_status(
        client=client,
        cluster_id=cluster.id,
        nodes_count=len(cluster.hosts),
        statuses=[consts.NodesStatus.INSTALLED],
        timeout=timeout,
        interval=60,
    )
    utils.wait_till_cluster_is_in_status(
        client=client, cluster_id=cluster.id, statuses=[consts.ClusterStatus.INSTALLED]
    )


# Runs installation flow :
# 1. Verifies cluster id exists
# 2. Running install cluster api
# 3. Waiting till all nodes are in installing status
# 4. Downloads kubeconfig for future usage
def run_install_flow(client, cluster_id, kubeconfig_path, pull_secret):
    log.info("Verifying cluster exists")
    cluster = client.cluster_get(cluster_id)
    log.info("Verifying pull secret")
    verify_pull_secret(client=client, cluster=cluster, pull_secret=pull_secret)
    log.info("Wait till cluster is ready")
    utils.wait_till_cluster_is_in_status(
        client=client,
        cluster_id=cluster_id,
        statuses=[consts.ClusterStatus.READY, consts.ClusterStatus.INSTALLING],
    )
    cluster = client.cluster_get(cluster_id)
    if cluster.status == consts.ClusterStatus.READY:
        log.info("Install cluster %s", cluster_id)
        _install_cluster(client=client, cluster=cluster)

    else:
        log.info("Cluster is already in installing status, skipping install command")

    log.info("Download kubeconfig-noingress")
    client.download_kubeconfig_no_ingress(
        cluster_id=cluster_id, kubeconfig_path=kubeconfig_path
    )

    wait_till_installed(client=client, cluster=cluster)

    log.info("Download kubeconfig")
    waiting.wait(
        lambda: client.download_kubeconfig(
            cluster_id=cluster_id, kubeconfig_path=kubeconfig_path
        )
        is None,
        timeout_seconds=240,
        sleep_seconds=20,
        expected_exceptions=Exception,
        waiting_for="Kubeconfig",
    )


def main():
    _verify_kube_download_folder(args.kubeconfig_path)
    log.info("Creating bm inventory client")
    # if not cluster id is given, reads it from latest run
    if not args.cluster_id:
        args.cluster_id = utils.get_tfvars()["cluster_inventory_id"]
    client = bm_inventory_api.create_client(wait_for_url=False)
    run_install_flow(
        client=client,
        cluster_id=args.cluster_id,
        kubeconfig_path=args.kubeconfig_path,
        pull_secret=args.pull_secret,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run discovery flow")
    parser.add_argument(
        "-id", "--cluster-id", help="Cluster id to install", type=str, default=None
    )
    parser.add_argument(
        "-k",
        "--kubeconfig-path",
        help="Path to downloaded kubeconfig",
        type=str,
        default="build/kubeconfig",
    )
    parser.add_argument(
        "-ps", "--pull-secret", help="Pull secret", type=str, default=""
    )
    args = parser.parse_args()
    main()
