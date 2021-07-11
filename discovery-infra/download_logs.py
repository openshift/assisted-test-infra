#!/usr/bin/env python3

import filecmp
import json
import os
import shutil
import tempfile
import time
from argparse import ArgumentParser
from collections import Counter
from contextlib import suppress
from datetime import datetime

import assisted_service_client
import requests
import urllib3
from dateutil.parser import isoparse
from paramiko.ssh_exception import SSHException
from scp import SCPException

from test_infra import warn_deprecate
from test_infra.tools.concurrently import run_concurrently
from test_infra.assisted_service_api import InventoryClient, create_client
from test_infra.consts import ClusterStatus, HostsProgressStages, env_defaults
from test_infra.controllers.node_controllers.node import Node
from test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from test_infra.helper_classes import cluster as helper_cluster
from test_infra.utils import (are_host_progress_in_stage, config_etc_hosts,
                              recreate_folder, run_command, verify_logs_uploaded, fetch_url)

from logger import log, suppressAndLog

private_ssh_key_path_default = os.path.join(os.getcwd(), str(env_defaults.DEFAULT_SSH_PRIVATE_KEY_PATH))

TIME_FORMAT = '%Y-%m-%d_%H:%M:%S'
MAX_RETRIES = 3
MUST_GATHER_MAX_RETRIES = 15
RETRY_INTERVAL = 60 * 5
CONNECTION_TIMEOUT = 30
SOSREPORT_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "resources",
    "man_sosreport.sh")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

warn_deprecate()


def main():
    args = handle_arguments()

    if args.sosreport:
        gather_sosreport_data(output_dir=args.dest)

    client = create_client(url=args.inventory_url, timeout=CONNECTION_TIMEOUT)
    if args.cluster_id:
        cluster = client.cluster_get(args.cluster_id)
        download_logs(client, json.loads(json.dumps(cluster.to_dict(), sort_keys=True, default=str)), args.dest,
                      args.must_gather, args.update_by_events, pull_secret=args.pull_secret)
    else:
        clusters = get_clusters(client, args.download_all)

        if not clusters:
            log.info('No clusters were found')
            return

        for cluster in clusters:
            if args.download_all or should_download_logs(cluster):
                download_logs(client, cluster, args.dest, args.must_gather, args.update_by_events,
                              pull_secret=args.pull_secret)

        log.info("Cluster installation statuses: %s",
                 dict(Counter(cluster["status"] for cluster in clusters).items()))


def get_clusters(client, all_cluster):
    if all_cluster:
        return client.get_all_clusters()

    return client.clusters_list()


def should_download_logs(cluster: dict):
    return cluster['status'] in [ClusterStatus.ERROR]


def min_number_of_log_files(cluster, is_controller_expected):
    if is_controller_expected:
        return len(cluster['hosts']) + 1

    return len(cluster['hosts'])


def is_update_needed(output_folder: str, update_on_events_update: bool, client: InventoryClient, cluster: dict):
    if not os.path.isdir(output_folder):
        return True

    if not update_on_events_update:
        return False

    destination_event_file_path = get_cluster_events_path(cluster, output_folder)
    with tempfile.NamedTemporaryFile() as latest_event_tp:
        with suppressAndLog(assisted_service_client.rest.ApiException):
            client.download_cluster_events(cluster['id'], latest_event_tp.name)

        if filecmp.cmp(destination_event_file_path, latest_event_tp.name):
            latest_event_tp.close()
            log.info("no new events found for {}".format(destination_event_file_path))
            need_update = False
        else:
            log.info("update needed, new events found, deleting {} ".format(destination_event_file_path))
            os.remove(destination_event_file_path)
            latest_event_tp.close()
            need_update = True
    return need_update


def download_logs(client: InventoryClient, cluster: dict, dest: str, must_gather: bool,
                  update_by_events: bool = False, retry_interval: int = RETRY_INTERVAL, pull_secret=""):

    if "hosts" not in cluster or len(cluster["hosts"]) == 0:
        cluster["hosts"] = client.get_cluster_hosts(cluster_id=cluster["id"])

    output_folder = get_logs_output_folder(dest, cluster)
    if not is_update_needed(output_folder, update_by_events, client, cluster):
        log.info(f"Skipping, no need to update {output_folder}.")
        return

    recreate_folder(output_folder)
    recreate_folder(os.path.join(output_folder, "cluster_files"))

    try:
        write_metadata_file(client, cluster, os.path.join(output_folder, 'metadata.json'))

        with suppressAndLog(AssertionError, ConnectionError, requests.exceptions.ConnectionError):
            client.download_metrics(os.path.join(output_folder, "metrics.txt"))

        for cluster_file in ("bootstrap.ign", "master.ign", "worker.ign", "install-config.yaml", "custom_manifests.yaml"):
            with suppressAndLog(assisted_service_client.rest.ApiException):
                client.download_and_save_file(cluster['id'], cluster_file,
                                              os.path.join(output_folder, "cluster_files", cluster_file))

        for host_id in map(lambda host: host['id'], cluster['hosts']):
            with suppressAndLog(assisted_service_client.rest.ApiException):
                client.download_host_ignition(cluster['id'], host_id, os.path.join(output_folder, "cluster_files"))

        with suppressAndLog(assisted_service_client.rest.ApiException):
            client.download_cluster_events(cluster['id'], get_cluster_events_path(cluster, output_folder))
            shutil.copy2(os.path.join(os.path.dirname(os.path.realpath(__file__)), "events.html"), output_folder)

        with suppressAndLog(assisted_service_client.rest.ApiException):
            are_masters_in_configuring_state = are_host_progress_in_stage(
                cluster['hosts'], [HostsProgressStages.CONFIGURING], 2)
            are_masters_in_join_state = are_host_progress_in_stage(
                cluster['hosts'], [HostsProgressStages.JOINED], 2)
            max_retries = MUST_GATHER_MAX_RETRIES if are_masters_in_join_state else MAX_RETRIES
            is_controller_expected = cluster['status'] == ClusterStatus.INSTALLED or are_masters_in_configuring_state
            min_number_of_logs = min_number_of_log_files(cluster, is_controller_expected)

            for i in range(max_retries):
                cluster_logs_tar = os.path.join(output_folder, f"cluster_{cluster['id']}_logs.tar")

                with suppress(FileNotFoundError):
                    os.remove(cluster_logs_tar)

                client.download_cluster_logs(cluster['id'], cluster_logs_tar)
                try:
                    verify_logs_uploaded(cluster_logs_tar, min_number_of_logs,
                                         installation_success=(cluster['status'] == ClusterStatus.INSTALLED),
                                         check_oc=are_masters_in_join_state)
                    break
                except AssertionError as ex:
                    log.warn(f"Cluster logs verification failed: {ex}")

                    # Skip sleeping on last retry
                    if i < MAX_RETRIES - 1:
                        log.info(f"Going to retry in {retry_interval} seconds")
                        time.sleep(retry_interval)

        kubeconfig_path = os.path.join(output_folder, "kubeconfig-noingress")

        with suppressAndLog(assisted_service_client.rest.ApiException):
            client.download_kubeconfig_no_ingress(cluster['id'], kubeconfig_path)

            if must_gather:
                recreate_folder(os.path.join(output_folder, "must-gather"))
                config_etc_hosts(cluster['name'], cluster['base_dns_domain'],
                                 helper_cluster.get_api_vip_from_cluster(client, cluster, pull_secret))
                download_must_gather(kubeconfig_path, os.path.join(output_folder, "must-gather"))

    finally:
        run_command(f"chmod -R ugo+rx '{output_folder}'")


def get_cluster_events_path(cluster, output_folder):
    return os.path.join(output_folder, f"cluster_{cluster['id']}_events.json")


def get_logs_output_folder(dest: str, cluster: dict):
    started_at = cluster['install_started_at']

    if isinstance(started_at, str):
        started_at = isoparse(started_at)

    if isinstance(started_at, datetime):
        started_at = started_at.strftime(TIME_FORMAT)

    return os.path.join(dest, f"{started_at}_{cluster['id']}")


def write_metadata_file(client: InventoryClient, cluster: dict, file_name: str):
    d = {'cluster': cluster}
    d.update(client.get_versions())

    with suppress(KeyError):
        d['link'] = f"{get_ui_url_from_api_url(client.inventory_url)}/clusters/{cluster['id']}"

    with open(file_name, 'w') as metadata_file:
        json.dump(d, metadata_file, sort_keys=True, indent=4)


def get_ui_url_from_api_url(api_url: str):
    known_urls = {
        'https://api.openshift.com/': 'https://cloud.redhat.com/openshift/assisted-installer',
        'https://api.stage.openshift.com/': 'https://qaprodauth.cloud.redhat.com/openshift',
    }

    for k, v in known_urls.items():
        if api_url in k:
            return v
    else:
        raise KeyError(api_url)


def download_must_gather(kubeconfig: str, dest_dir: str):
    log.info(f"Downloading must-gather to {dest_dir}")
    command = f"oc --insecure-skip-tls-verify --kubeconfig={kubeconfig} adm must-gather" \
              f" --dest-dir {dest_dir} > {dest_dir}/must-gather.log"
    try:
        run_command(command, shell=True, raise_errors=True)
    except RuntimeError as ex:
        log.warning(f"Failed to run must gather: {ex}")


def gather_sosreport_data(output_dir: str, private_ssh_key_path: str = private_ssh_key_path_default):
    sosreport_output = os.path.join(output_dir, "sosreport")
    recreate_folder(sosreport_output)

    controller = LibvirtController(private_ssh_key_path=private_ssh_key_path)
    run_concurrently(
        jobs=[(gather_sosreport_from_node, node, sosreport_output)
              for node in controller.list_nodes()],
        timeout=60 * 20,
    )


def gather_sosreport_from_node(node: Node, destination_dir: str):
    try:
        node.upload_file(SOSREPORT_SCRIPT, "/tmp/man_sosreport.sh")
        node.run_command("chmod a+x /tmp/man_sosreport.sh")
        node.run_command("sudo /tmp/man_sosreport.sh")
        node.download_file(f"/tmp/sosreport.tar.bz2",
                           os.path.join(destination_dir, f"sosreport-{node.name}.tar.bz2"))

    except (TimeoutError, RuntimeError, SSHException, SCPException):
        log.exception("Failed accessing node %s for sosreport data gathering", node)


def collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install):
    cluster_name = cluster_deployment.ref.name
    output_folder = f'build/{cluster_name}'
    recreate_folder(output_folder)
    aci = agent_cluster_install.get()
    debug_info = aci['status']['debugInfo']

    try:
        log.info("Collecting debugInfo (events/logs) from cluster")
        fetch_url_and_write_to_file('eventsURL', 'events.json', debug_info, output_folder)
        fetch_url_and_write_to_file('logsURL', 'logs.tar', debug_info, output_folder)
    except Exception as err:
        log.warning(f"Failed to collect debug info for cluster {cluster_name} ({err})")


def fetch_url_and_write_to_file(url_key, file_name, debug_info, output_folder):
    if url_key in debug_info:
        logsURL = debug_info[url_key]
        content = fetch_url(logsURL)
        output_file = os.path.join(output_folder, file_name)
        with open(output_file, "wb") as _file:
            _file.write(content)
    else:
        log.warning(f"{url_key} is not available")


def handle_arguments():
    parser = ArgumentParser(description="Download logs")

    parser.add_argument("inventory_url", help="URL of remote inventory", type=str)
    parser.add_argument("dest", help="Destination to download logs", type=str)
    parser.add_argument("--cluster-id", help="Cluster id to download its logs", type=str, default=None, nargs='?')
    parser.add_argument("--download-all", help="Download logs from all clusters", action='store_true')
    parser.add_argument("--must-gather", help="must-gather logs", action='store_true')
    parser.add_argument("--sosreport", help="gather sosreport from each node", action='store_true')
    parser.add_argument("--update-by-events", help="Update logs if cluster events were updated", action='store_true')
    parser.add_argument("-ps", "--pull-secret", help="Pull secret", type=str, default="")

    return parser.parse_args()


if __name__ == '__main__':
    main()
