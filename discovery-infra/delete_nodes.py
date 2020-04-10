#!/usr/bin/python3

import os
import argparse
import json
import consts
import utils
import virsh_cleanup
import bm_inventory_api


def try_to_delete_cluster(tfvars):
    try:
        cluster_id = tfvars.get("cluster_inventory_id")
        if cluster_id:
            client = bm_inventory_api.create_client()
            client.delete_cluster(cluster_id=cluster_id)
    # TODO add different exception validations
    except Exception as exc:
        print("Failed to delete cluster", str(exc))


def delete_nodes():
    try:
        print("Start running terraform delete")
        cmd = "make destroy_terraform"
        return utils.run_command_with_output(cmd)
    except:
        virsh_cleanup.clean_virsh_resources(virsh_cleanup.DEFAULT_SKIP_LIST, consts.TEST_INFRA)


def main():
    if not os.path.exists(consts.TFVARS_JSON_FILE):
        return
    with open(consts.TFVARS_JSON_FILE) as _file:
        tfvars = json.load(_file)
    if not args.only_nodes:
        try_to_delete_cluster(tfvars)
    delete_nodes()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run discovery flow')
    parser.add_argument('-n', '--only-nodes', help='Delete only nodes, without cluster', action="store_true")
    args = parser.parse_args()
    main()
