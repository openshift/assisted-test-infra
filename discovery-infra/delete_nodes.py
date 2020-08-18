#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import json
import argparse
import shutil
from functools import partial

import assisted_service_api
import consts
import utils
import oc_utils
import virsh_cleanup
from logger import log


@utils.on_exception(message='Failed to delete cluster')
def try_to_delete_cluster(namespace, tfvars):
    """ Try to delete cluster if assisted-service is up and such cluster
        exists.
    """
    cluster_id = tfvars.get('cluster_inventory_id')
    if not cluster_id:
        return

    args.namespace = namespace
    client = assisted_service_api.create_client(
        url=utils.get_assisted_service_url_by_args(args)
    )
    client.delete_cluster(cluster_id=cluster_id)


def delete_nodes(cluster_name, namespace, tf_folder, tfvars):
    """ Runs terraform destroy and then cleans it with virsh cleanup to delete
        everything relevant.
    """
    _try_to_delete_nodes(tf_folder)

    default_network_name = consts.TEST_NETWORK + namespace
    _delete_virsh_resources(
        tfvars.get('cluster_name', cluster_name),
        tfvars.get('libvirt_network_name', default_network_name),
    )

    log.info('Deleting %s', tf_folder)
    shutil.rmtree(tf_folder)


@utils.on_exception(
    message='Failed to run terraform delete',
    silent=True
)
def _try_to_delete_nodes(tf_folder):
    log.info('Start running terraform delete')
    utils.run_command_with_output(
        f'cd {tf_folder} && '
        'terraform destroy '
        '-auto-approve '
        '-input=false '
        '-state=terraform.tfstate ' 
        '-state-out=terraform.tfstate ' 
        '-var-file=terraform.tfvars.json'
    )


def _delete_virsh_resources(*filters):
    log.info('Deleting virsh resources (filters: %s)', filters)
    virsh_cleanup.clean_virsh_resources(
        skip_list=virsh_cleanup.DEFAULT_SKIP_LIST,
        resource_filter=filters
    )


@utils.on_exception(
    message='Failed to delete clusters from namespaces',
    silent=True
)
def delete_clusters_from_all_namespaces():
    for name, namespace in utils.get_all_namespaced_clusters():
        delete_cluster(name, namespace)


@utils.on_exception(message='Failed to delete nodes', silent=True)
def delete_cluster(cluster_name, namespace):
    log.info(
        'Deleting cluster: %s in namespace: %s',
        cluster_name, namespace
    )

    tf_folder = utils.get_tf_folder(cluster_name, namespace)
    tfvars = utils.get_tfvars(tf_folder)

    if not args.only_nodes:
        try_to_delete_cluster(namespace, tfvars)
    delete_nodes(cluster_name, namespace, tf_folder, tfvars)


def main():
    if args.delete_all:
        _delete_virsh_resources()
        return

    if args.namespace == 'all':
        delete_clusters_from_all_namespaces()
        return

    cluster_name = f'{args.cluster_name or consts.CLUSTER_PREFIX}-{args.namespace}'
    delete_cluster(cluster_name, args.namespace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run delete nodes flow")
    parser.add_argument(
        "-iU",
        "--inventory-url",
        help="Full url of remote inventory",
        type=str,
        default="",
    )
    parser.add_argument(
        "-id", "--cluster-id", help="Cluster id to install", type=str, default=None
    )
    parser.add_argument(
        "-n",
        "--only-nodes",
        help="Delete only nodes, without cluster",
        action="store_true",
    )
    parser.add_argument(
        "-a",
        "--delete-all",
        help="Delete only nodes, without cluster",
        action="store_true",
    )
    parser.add_argument(
        "-ns",
        "--namespace",
        help="Delete under this namespace",
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
        required=False,
    )
    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    main()
