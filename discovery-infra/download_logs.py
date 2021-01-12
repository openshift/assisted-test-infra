#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import time
from argparse import ArgumentParser
from collections import Counter
from contextlib import suppress
from datetime import datetime

import assisted_service_client
import urllib3
from dateutil.parser import isoparse

from logger import log
from test_infra.assisted_service_api import InventoryClient, create_client
from test_infra.consts import ClusterStatus
from test_infra.logs_utils import verify_logs_uploaded
from test_infra.utils import config_etc_hosts, recreate_folder, run_command

TIME_FORMAT = '%Y-%m-%d_%H:%M:%S'
MAX_RETRIES = 3
RETRY_INTERVAL = 60 * 5

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main():
    args = handle_arguments()
    client = create_client(url=args.inventory_url)

    if args.cluster_id:
        cluster = client.cluster_get(args.cluster_id)
        download_logs(client, json.loads(json.dumps(cluster.to_dict(), sort_keys=True, default=str)), args.dest, args.must_gather)
    else:
        clusters = client.clusters_list()

        if not clusters:
            log.info('No clusters were found')
            return

        for cluster in clusters:
            if args.download_all or should_download_logs(cluster):
                download_logs(client, cluster, args.dest, args.must_gather)

        print(Counter(map(lambda cluster: cluster['status'], clusters)))


def should_download_logs(cluster: dict):
    return cluster['status'] in [ClusterStatus.ERROR]


def download_logs(client: InventoryClient, cluster: dict, dest: str, must_gather: bool, retry_interval: int = RETRY_INTERVAL):
    output_folder = get_logs_output_folder(dest, cluster)

    if os.path.isdir(output_folder):
        log.info(f"Skipping. The logs directory {output_folder} already exists.")
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
            client.download_cluster_events(cluster['id'], os.path.join(output_folder, f"cluster_{cluster['id']}_events.json"))
            shutil.copy2(os.path.join(os.path.dirname(os.path.realpath(__file__)), "events.html"), output_folder)

        with suppress(assisted_service_client.rest.ApiException):
            for i in range(MAX_RETRIES):
                cluster_logs_tar = os.path.join(output_folder, f"cluster_{cluster['id']}_logs.tar")

                with suppress(FileNotFoundError):
                    os.remove(cluster_logs_tar)

                client.download_cluster_logs(cluster['id'], cluster_logs_tar)

                min_number_of_logs = len(cluster['hosts']) + 1 if cluster['status'] == ClusterStatus.INSTALLED else len(cluster['hosts'])

                try:
                    verify_logs_uploaded(cluster_logs_tar, min_number_of_logs, cluster['status'] == ClusterStatus.INSTALLED)
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
                config_etc_hosts(cluster['name'], cluster['base_dns_domain'], cluster['api_vip'])
                download_must_gather(kubeconfig_path, os.path.join(output_folder, "must-gather"))
    finally:
        run_command(f"chmod -R ugo+rx '{output_folder}'")


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

    return parser.parse_args()


if __name__ == '__main__':
    main()
