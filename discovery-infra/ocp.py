#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import sys

from test_infra import assisted_service_api, utils, consts, warn_deprecate

import day2
import oc_utils

warn_deprecate()


def get_ocp_cluster(args):
    if not args.cluster_id:
        cluster_name = f'{args.cluster_name or consts.CLUSTER_PREFIX}-{args.namespace}'
        tf_folder = utils.get_tf_folder(cluster_name, args.namespace)
        args.cluster_id = utils.get_tfvars(tf_folder).get('cluster_inventory_id')
    client = assisted_service_api.create_client(
        url=utils.get_assisted_service_url_by_args(args=args)
    )
    return client.cluster_get(cluster_id=args.cluster_id)


def main(args):
    if args.config_etc_hosts:
        ocp_cluster = get_ocp_cluster(args)
        ocp_cluster_name = ocp_cluster.name
        ocp_api_vip_dnsname = f"api.{ocp_cluster_name}.{ocp_cluster.base_dns_domain}"
        day2.config_etc_hosts(ocp_cluster.api_vip, ocp_api_vip_dnsname)
    if args.get_cluster_api_vip:
        ocp_cluster = get_ocp_cluster(args)
        sys.stdout.write(ocp_cluster.api_vip)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCP")
    parser.add_argument(
        "-id", "--cluster-id",
        help="Cluster id to install",
        type=str,
        default=None
    )
    parser.add_argument(
        "-cn", "--cluster-name",
        help="Cluster name",
        type=str,
        default=""
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
        '--deploy-target',
        help='Where assisted-service is deployed',
        type=str,
        default='minikube'
    )
    parser.add_argument(
        "--config-etc-hosts",
        help="Config /etc/hosts file",
        action="store_true"
    )
    parser.add_argument(
        "--get-cluster-api-vip",
        help="Get OCP cluster API VIP",
        action="store_true"
    )
    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    main(args)
