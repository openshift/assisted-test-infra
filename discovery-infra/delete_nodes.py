#!/usr/bin/python3

import argparse
import consts
import utils
import virsh_cleanup
import bm_inventory_api


def try_to_delete_cluster(tfvars):
    try:
        cluster_id = tfvars.get("cluster_inventory_id")
        if cluster_id:
            client = bm_inventory_api.create_client(wait_for_url=False)
            client.delete_cluster(cluster_id=cluster_id)
    # TODO add different exception validations
    except Exception as exc:
        print("Failed to delete cluster", str(exc))


def delete_nodes(tfvars):
    try:
        print("Start running terraform delete")
        cmd = "cd build/terraform/  && terraform destroy -auto-approve " \
              "-input=false -state=terraform.tfstate -state-out=terraform.tfstate -var-file=terraform.tfvars.json"
        utils.run_command_with_output(cmd)
    except:
        print("Failed to run terraform delete")
    finally:
        virsh_cleanup.clean_virsh_resources(virsh_cleanup.DEFAULT_SKIP_LIST,
                                            [tfvars.get("cluster_name", consts.TEST_INFRA),
                                             tfvars.get("libvirt_network_name", consts.TEST_INFRA)])


def delete_all():
    print("Deleting all virsh resources")
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
            print("Failed to delete nodes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run delete nodes flow')
    parser.add_argument('-n', '--only-nodes', help='Delete only nodes, without cluster', action="store_true")
    parser.add_argument('-a', '--delete-all', help='Delete only nodes, without cluster', action="store_true")
    args = parser.parse_args()
    main()
