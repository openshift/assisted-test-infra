#!/usr/bin/env python3

import json
import os
import shutil
import tempfile
import subprocess
import time
import filecmp
from argparse import ArgumentParser
from collections import Counter
from contextlib import suppress
from datetime import datetime
import assisted_service_client
import urllib3
from dateutil.parser import isoparse

from logger import log
from test_infra.assisted_service_api import InventoryClient, create_client
from test_infra.helper_classes import cluster as helper_cluster
from test_infra.consts import ClusterStatus, HostsProgressStages
from test_infra.logs_utils import verify_logs_uploaded

from test_infra.utils import config_etc_hosts, recreate_folder, run_command, are_host_progress_in_stage

TIME_FORMAT = '%Y-%m-%d_%H:%M:%S'
MAX_RETRIES = 3
RETRY_INTERVAL = 60 * 5

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main():
    args = handle_arguments()
    client = create_client(url=args.inventory_url)

    if args.cluster_id:
        cluster = client.cluster_get(args.cluster_id)
        download_logs(client, json.loads(json.dumps(cluster.to_dict(), sort_keys=True, default=str)), args.dest, args.must_gather, args.update_by_events)
    else:
        clusters = get_clusters(client, args.download_all)

        if not clusters:
            log.info('No clusters were found')
            return

        for cluster in clusters:
            if args.download_all or should_download_logs(cluster):
                download_logs(client, cluster, args.dest, args.must_gather, args.update_by_events)

        print(Counter(map(lambda cluster: cluster['status'], clusters)))


def get_clusters(client, all_cluster):
    if all_cluster:
        return client.get_all_clusters()
    else:
        return client.clusters_list()


def should_download_logs(cluster: dict):
    return cluster['status'] in [ClusterStatus.ERROR]

def min_number_of_log_files(cluster, is_controller_expected):
    if is_controller_expected:
        return len(cluster['hosts']) + 1
    else:
        return  len(cluster['hosts'])

def is_update_needed(output_folder: str, update_on_events_update: bool, client: InventoryClient, cluster: dict):

    if not os.path.isdir(output_folder):
        return True
    if not update_on_events_update:
        return False

    destination_event_file_path = get_cluster_events_path(cluster, output_folder)
    with tempfile.NamedTemporaryFile() as latest_event_tp:
        with suppress(assisted_service_client.rest.ApiException):
            client.download_cluster_events(cluster['id'], latest_event_tp.name)

        if filecmp.cmp(destination_event_file_path, latest_event_tp.name):
            latest_event_tp.close()
            log.info("no new events found for {}".format(destination_event_file_path))
            need_update =  False
        else:
            log.info("update needed, new events found, deleting {} ".format(destination_event_file_path))
            os.remove(destination_event_file_path)
            latest_event_tp.close()
            need_update = True
    return need_update

def download_logs(client: InventoryClient, cluster: dict, dest: str, must_gather: bool, update_by_events: bool = False, retry_interval: int = RETRY_INTERVAL):
    output_folder = get_logs_output_folder(dest, cluster)
    if not is_update_needed(output_folder, update_by_events, client, cluster):
        log.info(f"Skipping, no need to update {output_folder}.")
        return

    recreate_folder(output_folder)
    recreate_folder(os.path.join(output_folder, "cluster_files"))

    try:
        write_metadata_file(client, cluster, os.path.join(output_folder, 'metdata.json'))

        with suppress(assisted_service_client.rest.ApiException):
            client.download_ignition_files(cluster['id'], os.path.join(output_folder, "cluster_files"))

        for host_id in map(lambda host: host['id'], cluster['hosts']):
            with suppress(assisted_service_client.rest.ApiException):
                client.download_host_ignition(cluster['id'], host_id, os.path.join(output_folder, "cluster_files"))

        with suppress(assisted_service_client.rest.ApiException):
            client.download_cluster_events(cluster['id'], get_cluster_events_path(cluster, output_folder))
            shutil.copy2(os.path.join(os.path.dirname(os.path.realpath(__file__)), "events.html"), output_folder)

        with suppress(assisted_service_client.rest.ApiException):
            are_masters_in_configuring_state = are_host_progress_in_stage(
                cluster['hosts'], [HostsProgressStages.CONFIGURING], 2)
            are_masters_in_join_state = are_host_progress_in_stage(
                cluster['hosts'], [HostsProgressStages.JOINED], 2)
            max_retries = 2*MAX_RETRIES if are_masters_in_join_state else MAX_RETRIES
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

        with suppress(assisted_service_client.rest.ApiException):
            client.download_kubeconfig_no_ingress(cluster['id'], kubeconfig_path)

            if must_gather:
                recreate_folder(os.path.join(output_folder, "must-gather"))
                config_etc_hosts(cluster['name'], cluster['base_dns_domain'],
                                 helper_cluster.get_api_vip_from_cluster(client, cluster))
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
    command = f"oc --insecure-skip-tls-verify --kubeconfig={kubeconfig} adm must-gather --dest-dir {dest_dir} > {dest_dir}/must-gather.log"
    subprocess.run(command, shell=True)


def handle_arguments():
    parser = ArgumentParser(description="Download logs")

    parser.add_argument("inventory_url", help="URL of remote inventory", type=str)
    parser.add_argument("dest", help="Destination to download logs", type=str)
    parser.add_argument("--cluster-id", help="Cluster id to download its logs", type=str, default=None, nargs='?')
    parser.add_argument("--download-all", help="Download logs from all clusters", action='store_true')
    parser.add_argument("--must-gather", help="must-gather logs", action='store_true')
    parser.add_argument("--update-by-events", help="Update logs if cluster events were updated", action='store_true')

    return parser.parse_args()


if __name__ == '__main__':
    main()
