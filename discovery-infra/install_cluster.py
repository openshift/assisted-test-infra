#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import argparse

import assisted_service_api
import consts
import utils
import oc_utils
import waiting
from logger import log
from test_infra.tools import terraform_utils


# Verify folder to download kubeconfig exists. If will be needed in other places move to utils
def _verify_kube_download_folder(kubeconfig_path):
    if not utils.folder_exists(kubeconfig_path):
        exit(1)


def verify_pull_secret(cluster, client, pull_secret):
    if not cluster.pull_secret_set and not pull_secret:
        raise Exception("Can't install cluster %s, no pull secret was set" % cluster.id)
    if not cluster.pull_secret_set and pull_secret:
        client.update_cluster(cluster.id, {"pull_secret": pull_secret})


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
        statuses=[
            consts.NodesStatus.INSTALLING,
            consts.NodesStatus.INSTALLING_IN_PROGRESS,
        ],
        interval=30,
    )


def wait_till_installed(client, cluster, timeout=60 * 60 * 2):
    log.info("Waiting %s till cluster finished installation", timeout)
    # TODO: Change host validation for only previous known hosts
    try:
        utils.wait_till_all_hosts_are_in_status(
            client=client,
            cluster_id=cluster.id,
            nodes_count=len(cluster.hosts),
            statuses=[consts.NodesStatus.INSTALLED],
            timeout=timeout,
            interval=60,
        )
        utils.wait_till_cluster_is_in_status(
            client=client,
            cluster_id=cluster.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
        )
    finally:
        output_folder = f'build/{cluster.id}'
        utils.recreate_folder(output_folder)
        download_logs_from_all_hosts(client=client, cluster_id=cluster.id, output_folder=output_folder)


# Runs installation flow :
# 1. Verifies cluster id exists
# 2. Running install cluster api
# 3. Waiting till all nodes are in installing status
# 4. Downloads kubeconfig for future usage
def run_install_flow(client, cluster_id, kubeconfig_path, pull_secret, tf=None):
    log.info("Verifying cluster exists")
    cluster = client.cluster_get(cluster_id)
    client.update_cluster_install_config(cluster_id, {"networking": {"networkType": "OpenShiftSDN"}})
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

    # set new vips
    if tf:
        cluster_info = client.cluster_get(cluster.id)
        tf.set_new_vip(cluster_info.api_vip)


def download_logs_from_all_hosts(client, cluster_id, output_folder):
    hosts = client.get_cluster_hosts(cluster_id=cluster_id)
    for host in hosts:
        output_file = os.path.join(output_folder, f'host_{host["id"]}.tar.gz')
        waiting.wait(
            lambda: client.download_host_logs(cluster_id=cluster_id,
                                              host_id=host["id"],
                                              output_file=output_file) is None,
            timeout_seconds=240,
            sleep_seconds=20,
            expected_exceptions=Exception,
            waiting_for="Logs",
        )


def main():
    _verify_kube_download_folder(args.kubeconfig_path)
    log.info("Creating assisted service client")
    # if not cluster id is given, reads it from latest run
    tf = None
    if not args.cluster_id:
        cluster_name = f'{args.cluster_name or consts.CLUSTER_PREFIX}-{args.namespace}'
        tf_folder = utils.get_tf_folder(cluster_name, args.namespace)
        args.cluster_id = utils.get_tfvars(tf_folder)['cluster_inventory_id']
        tf = terraform_utils.TerraformUtils(working_dir=tf_folder)

    client = assisted_service_api.create_client(
        url=utils.get_assisted_service_url_by_args(
            args=args,
            wait=False
        )
    )
    run_install_flow(
        client=client,
        cluster_id=args.cluster_id,
        kubeconfig_path=args.kubeconfig_path,
        pull_secret=args.pull_secret,
        tf=tf
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
    parser.add_argument(
        "-ns",
        "--namespace",
        help="Namespace to use",
        type=str,
        default="assisted-installer",
    )
    parser.add_argument(
        '--service-name',
        help='Override assisted-service target service name',
        type=str,
        default='assisted-service'
    )
    parser.add_argument(
        '-cn',
        '--cluster-name',
        help='Cluster name',
        required=False
    )
    parser.add_argument(
        '--profile',
        help='Minikube profile for assisted-installer deployment',
        type=str,
        default='assisted-installer'
    )
    parser.add_argument(
        '--deploy-target',
        help='Where assisted-service is deployed',
        type=str,
        default='minikube'
    )
    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    main()
