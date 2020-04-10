#!/usr/bin/python3

import argparse
import subprocess

DEFAULT_SKIP_LIST = ["default"]


def run_command(command, check=False, resource_filter=None):
    if resource_filter:
        command += "| grep %s" % resource_filter
    process = subprocess.run(command, shell=True, check=check, stdout=subprocess.PIPE, universal_newlines=True)
    output = process.stdout.strip()
    return output


def clean_domains(skip_list, resource_filter):
    domains = run_command("virsh list --all --name", resource_filter=resource_filter)
    domains = domains.splitlines()
    for domain in domains:
        print("Deleting domain ", domain)
        if domain and domain not in skip_list:
            run_command("virsh destroy %s" % domain, check=False)
            run_command("virsh undefine %s" % domain, check=False)


def clean_volumes(pool):
    volumes_with_path = run_command("virsh vol-list %s | tail -n +3" % pool).splitlines()
    for volume_with_path in volumes_with_path:
        volume, _ = volume_with_path.split()
        if volume:
            print("Deleting volume ", volume, "in pool ", pool)
            run_command("virsh vol-delete --pool %s %s" % (pool, volume), check=False)


def clean_pools(skip_list, resource_filter):
    pools = run_command("virsh pool-list --all --name", resource_filter=resource_filter)
    pools = pools.splitlines()
    for pool in pools:
        if pool and pool not in skip_list:
            clean_volumes(pool)
            print("Deleting pool ", pool)
            run_command("virsh pool-destroy %s" % pool, check=False)
            run_command("virsh pool-undefine %s" % pool, check=False)


def clean_networks(skip_list, resource_filter):
    networks = run_command("virsh net-list --all --name", resource_filter=resource_filter)
    networks = networks.splitlines()
    for net in networks:
        if net and net not in skip_list:
            print("Deleting network ", net)
            run_command("virsh net-destroy %s" % net, check=False)
            run_command("virsh net-undefine %s" % net, check=False)


def clean_virsh_resources(skip_list, resource_filter):
    clean_domains(skip_list, resource_filter)
    clean_pools(skip_list, resource_filter)
    clean_networks(skip_list, resource_filter)


def main(p_args):
    skip_list = DEFAULT_SKIP_LIST
    resource_filter = None
    if p_args.minikube:
        resource_filter = "minikube"
    if p_args.filter:
        resource_filter = p_args.filter
    else:
        skip_list.extend(["minikube", "minikube-net"])

    clean_virsh_resources(skip_list, resource_filter)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Description of your program')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-a', '--all', help='Clean all virsh resources', action="store_true")
    group.add_argument('-m', '--minikube', help='Clean minikube resources', action="store_true")
    group.add_argument('-sm', '--skip-minikube', help='Clean all but skip minikube resources', action="store_true")
    group.add_argument('-f', '--filter', help='Clean all but skip minikube resources', action="store_true")
    args = parser.parse_args()
    main(args)
