#!/usr/bin/python3

import argparse
from pathlib import Path
import utils
import consts
import bm_inventory_api


def _verify_kube_download_folder(kubeconfig_path):
    kube_dir = Path(kubeconfig_path).parent
    if not kube_dir:
        print("Directory", kube_dir, "doesn't exist. Please create it")
        exit(1)


def run_install_flow(client, cluster_id, kubeconfig_path):
    print("Verifying cluster exists")
    client.cluster_get(cluster_id)
    print("Install cluster", cluster_id)
    cluster = client.install_cluster(cluster_id=cluster_id)
    utils.wait_till_all_hosts_are_in_status(client=client, cluster_id=cluster_id,
                                            nodes_count=len(cluster.hosts), status=consts.NodesStatus.INSTALLING)

    print("Download kubeconfig")
    client.download_kubeconfig(cluster_id=cluster_id, kubeconfig_path=kubeconfig_path)


def main():
    _verify_kube_download_folder(args.kubeconfig_path)
    print("Creating bm inventory client")
    if not args.cluster_id:
        args.cluster_id = utils.get_tfvars()["cluster_inventory_id"]
    client = bm_inventory_api.create_client(wait_for_url=False)
    run_install_flow(client=client, cluster_id=args.cluster_id, kubeconfig_path=args.kubeconfig_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run discovery flow')
    parser.add_argument('-id', '--cluster-id', help='Cluster id to install', type=str, default=None)
    parser.add_argument('-k', '--kubeconfig-path', help='Path to downloaded kubeconfig', type=str,
                        default="build/kubeconfig")
    args = parser.parse_args()
    main()
