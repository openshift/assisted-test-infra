import subprocess

from logger import log
from test_infra import utils

DEFAULT_SKIP_LIST = ["default"]


def _run_command(command, check=False, resource_filter=None):
    if resource_filter:
        command += '| grep -E "%s"' % "|".join(resource_filter)
    process = subprocess.run(
        command,
        shell=True,
        check=check,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    output = process.stdout.strip()
    return output


def _clean_domains(skip_list, resource_filter):
    domains = _run_command(
        "virsh -c qemu:///system list --all --name", resource_filter=resource_filter
    )
    domains = domains.splitlines()
    for domain in domains:
        log.info("Deleting domain %s", domain)
        if domain and domain not in skip_list:
            _run_command("virsh -c qemu:///system destroy %s" % domain, check=False)
            _run_command("virsh -c qemu:///system undefine %s" % domain, check=False)


def _clean_volumes(pool):
    volumes_with_path = _run_command(
        "virsh -c qemu:///system vol-list %s | tail -n +3" % pool
    ).splitlines()
    for volume_with_path in volumes_with_path:
        volume, _ = volume_with_path.split()
        if volume:
            log.info("Deleting volume %s in pool %s", volume, pool)
            _run_command(
                "virsh -c qemu:///system vol-delete --pool %s %s" % (pool, volume),
                check=False,
            )


def _clean_pools(skip_list, resource_filter):
    pools = _run_command(
        "virsh -c qemu:///system pool-list --all --name",
        resource_filter=resource_filter,
    )
    pools = pools.splitlines()
    for pool in pools:
        if pool and pool not in skip_list:
            _clean_volumes(pool)
            log.info("Deleting pool %s", pool)
            _run_command("virsh -c qemu:///system pool-destroy %s" % pool, check=False)
            _run_command("virsh -c qemu:///system pool-undefine %s" % pool, check=False)


def _clean_networks(skip_list, resource_filter):
    networks = _run_command(
        "virsh -c qemu:///system net-list --all --name", resource_filter=resource_filter
    )
    networks = networks.splitlines()
    for net in networks:
        if net and net not in skip_list:
            log.info("Deleting network %s", net)
            _run_command("virsh -c qemu:///system net-destroy %s" % net, check=False)
            _run_command("virsh -c qemu:///system net-undefine %s" % net, check=False)


def clean_virsh_resources(skip_list, resource_filter):
    with utils.file_lock_context():
        _clean_domains(skip_list, resource_filter)
        _clean_pools(skip_list, resource_filter)
        _clean_networks(skip_list, resource_filter)
