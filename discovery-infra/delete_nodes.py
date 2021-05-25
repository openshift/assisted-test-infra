#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import os
import shutil
import re

from distutils.util import strtobool

from kubernetes.client import CoreV1Api

from test_infra import assisted_service_api, utils, consts, warn_deprecate
from test_infra.controllers.nat_controller import NatController
from test_infra.helper_classes.kube_helpers import create_kube_api_client
from test_infra.utils.kubeapi_utils import delete_kube_api_resources_for_namespace

import oc_utils
import virsh_cleanup
from logger import log

warn_deprecate()


@utils.on_exception(message='Failed to delete cluster', silent=True)
def try_to_delete_cluster(namespace, tfvars):
    """ Try to delete cluster if assisted-service is up and such cluster
        exists.
    """
    cluster_id = tfvars.get('cluster_inventory_id')
    if args.kube_api or not cluster_id:
        return

    args.namespace = namespace
    client = assisted_service_api.create_client(
        url=utils.get_assisted_service_url_by_args(args=args, wait=False)
    )
    client.delete_cluster(cluster_id=cluster_id)

def _get_namespace_index(libvirt_network_if):
    # Hack to retrieve namespace index - does not exist in tests
    matcher = re.match(r'^tt(\d+)$', libvirt_network_if)
    return int(matcher.groups()[0]) if matcher is not None else 0

@utils.on_exception(message='Failed to remove nat', silent=True)
def _try_remove_nat(tfvars):
    primary_interface = tfvars.get('libvirt_network_if')
    if primary_interface is None:
        raise Exception("Could not get primary interface")
    secondary_interface = tfvars.get('libvirt_secondary_network_if', f's{primary_interface}')
    nat_controller = NatController([primary_interface, secondary_interface], _get_namespace_index(primary_interface))
    nat_controller.remove_nat_rules()

def delete_nodes(cluster_name, namespace, tf_folder, tfvars):
    """ Runs terraform destroy and then cleans it with virsh cleanup to delete
        everything relevant.
    """
    _try_remove_nat(tfvars)
    if os.path.exists(tf_folder):
        _try_to_delete_nodes(tf_folder)

    default_network_name = consts.TEST_NETWORK + namespace
    default_sec_network_name = consts.TEST_SECONDARY_NETWORK + namespace
    _delete_virsh_resources(
        tfvars.get('cluster_name', cluster_name),
        tfvars.get('libvirt_network_name', default_network_name),
        tfvars.get('libvirt_secondary_network_name', default_sec_network_name),
    )
    if os.path.exists(tf_folder):
        log.info('Deleting %s', tf_folder)
        shutil.rmtree(tf_folder)


@utils.on_exception(
    message='Failed to run terraform delete',
    silent=True
)
def _try_to_delete_nodes(tf_folder):
    log.info('Start running terraform delete')
    with utils.file_lock_context():
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


@utils.on_exception(message='Failed to delete cluster', silent=True)
def delete_cluster(cluster_name, namespace):
    log.info(
        'Deleting cluster: %s in namespace: %s',
        cluster_name, namespace
    )

    tfvars = {}
    tf_folder = utils.get_tf_folder(cluster_name, namespace)
    if os.path.exists(tf_folder):
        tfvars = utils.get_tfvars(tf_folder)

    if not args.only_nodes:
        try_to_delete_cluster(namespace, tfvars)
    delete_nodes(cluster_name, namespace, tf_folder, tfvars)


@utils.on_exception(message='Failed to delete kube api resources', silent=True)
def delete_kube_api_resources_from_namespaces(namespace):
    kube_api_client = create_kube_api_client()

    if namespace != 'all':
        return delete_kube_api_resources_for_namespace(
            kube_api_client=kube_api_client,
            name=f'{args.cluster_name or consts.CLUSTER_PREFIX}-{namespace}',
            namespace=namespace
        )

    v1 = CoreV1Api(kube_api_client)
    for namespace in v1.list_namespace():
        return delete_kube_api_resources_for_namespace(
            kube_api_client=kube_api_client,
            name=f'{args.cluster_name or consts.CLUSTER_PREFIX}-{namespace}',
            namespace=namespace
        )


@utils.on_exception(
    message='Failed to delete nodes',
    silent=True,
    errors=(FileNotFoundError,)
)
def main():
    if args.kube_api:
        delete_kube_api_resources_from_namespaces(args.namespace)

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
        required=False
    )
    parser.add_argument(
        '--deploy-target',
        help='Where assisted-service is deployed',
        type=str,
        default='minikube'
    )
    parser.add_argument(
        "--kube-api",
        help="Should kube-api interface be used for cluster deployment",
        type=strtobool,
        nargs='?',
        const=True,
        default=False,
    )
    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    main()
