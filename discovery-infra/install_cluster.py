#!/usr/bin/python3

import argparse
from pathlib import Path
import utils
import consts
import bm_inventory_api
from logger import log


# Verify folder to download kubeconfig exists. If will be needed in other places move to utils
def _verify_kube_download_folder(kubeconfig_path):
    if not utils.folder_exists(kubeconfig_path):
        exit(1)


# Runs installation flow :
# 1. Verifies cluster id exists
# 2. Running install cluster api
# 3. Waiting till all nodes are in installing status
# 4. Downloads kubeconfig for future usage
def run_install_flow(client, cluster_id, kubeconfig_path):
    log.info("Verifying cluster exists")
    cluster = client.cluster_get(cluster_id)
    if not cluster.pull_secret:
        raise Exception("Can't install cluster %s, no pull secret was set" % cluster_id)
    log.info("Install cluster %s", cluster_id)
    cluster = client.install_cluster(cluster_id=cluster_id)
    utils.wait_till_all_hosts_are_in_status(client=client, cluster_id=cluster_id,
                                            nodes_count=len(cluster.hosts), status=consts.NodesStatus.INSTALLING)

    log.info("Download kubeconfig")
    client.download_kubeconfig_no_ingress(cluster_id=cluster_id, kubeconfig_path=kubeconfig_path)


def main():
    _verify_kube_download_folder(args.kubeconfig_path)
    log.info("Creating bm inventory client")
    # if not cluster id is given, reads it from latest run
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
