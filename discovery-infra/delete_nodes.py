#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import shutil

import assisted_service_api
import consts
import utils
import oc_utils
import virsh_cleanup
from logger import log


# Try to delete cluster if assisted-service is up and such cluster exists
def try_to_delete_cluster(tfvars):
    try:
        cluster_id = tfvars.get("cluster_inventory_id")
        if cluster_id:
            client = assisted_service_api.create_client(
                url=utils.get_assisted_service_url_by_args(
                    args=args,
                    wait=False
                )
            )
            client.delete_cluster(cluster_id=cluster_id)
    # TODO add different exception validations
    except:
        log.exception("Failed to delete cluster")


# Runs terraform destroy and then cleans it with virsh cleanup to delete everything relevant
def delete_nodes(tfvars):
    try:
        log.info("Start running terraform delete")
        cmd = (
            "cd %s  && terraform destroy -auto-approve "
            "-input=false -state=terraform.tfstate -state-out=terraform.tfstate "
            "-var-file=terraform.tfvars.json" % consts.TF_FOLDER
        )
        utils.run_command_with_output(cmd)
    except:
        log.exception("Failed to run terraform delete, deleting %s", consts.TF_FOLDER)
        shutil.rmtree(consts.TF_FOLDER)
    finally:
        virsh_cleanup.clean_virsh_resources(
            virsh_cleanup.DEFAULT_SKIP_LIST,
            [
                tfvars.get("cluster_name", consts.TEST_INFRA),
                tfvars.get("libvirt_network_name", consts.TEST_INFRA),
            ],
        )


# Deletes every single virsh resource, leaves only defaults
def delete_all():
    log.info("Deleting all virsh resources")
    virsh_cleanup.clean_virsh_resources(virsh_cleanup.DEFAULT_SKIP_LIST, None)


def main():
    if args.delete_all:
        delete_all()
    else:
        try:
            tfvars = utils.get_tfvars()
            if not args.only_nodes:
                try_to_delete_cluster(tfvars)
            delete_nodes(tfvars)
        except:
            log.exception("Failed to delete nodes")


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
    oc_utils.extend_parser_with_oc_arguments(parser)
    args = parser.parse_args()
    main()
