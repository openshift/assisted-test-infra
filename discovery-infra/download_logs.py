#!/usr/bin/env python3

import os
import json
from datetime import datetime
from dateutil.parser import isoparse
from argparse import ArgumentParser
from contextlib import suppress

from logger import log
from utils import recreate_folder, run_command
import assisted_service_client
from assisted_service_api import create_client, InventoryClient

FAILED_STATUSES = ["error"]
TIME_FORMAT = '%Y-%m-%d_%H:%M:%S'


def main():
    args = handle_arguments()
    client = create_client(url=args.inventory_url)

    if args.cluster_id:
        cluster = client.cluster_get(args.cluster_id)
        download_logs(client, json.loads(json.dumps(cluster.to_dict(), sort_keys=True, default=str)), args.dest)
    else:
        clusters = client.clusters_list()

        if not clusters:
            log.info('No clusters were found')
            return

        for cluster in clusters:
            if should_download_logs(cluster):
                download_logs(client, cluster, args.dest)


def should_download_logs(cluster: dict):
    return cluster['status'] in FAILED_STATUSES


def download_logs(client: InventoryClient, cluster: dict, dest: str):
    output_folder = get_logs_output_folder(dest, cluster)

    if os.path.isdir(output_folder):
        log.info(f"Skipping. The logs direct {output_folder} already exists.")
        return

    recreate_folder(output_folder)

    write_metadata_file(client, cluster, os.path.join(output_folder, 'metdata.json'))

    with suppress(assisted_service_client.rest.ApiException):
        client.download_cluster_events(cluster['id'], os.path.join(output_folder, f"cluster_{cluster['id']}_events.json"))

    with suppress(assisted_service_client.rest.ApiException):
        client.download_cluster_logs(cluster['id'], os.path.join(output_folder, f"cluster_{cluster['id']}_logs.tar"))

    run_command("chmod -R ugo+rx '%s'" % output_folder)


def get_logs_output_folder(dest: str, cluster: dict):
    started_at = cluster['install_started_at']

    if isinstance(started_at, str):
        started_at = isoparse(started_at)

    if isinstance(started_at, datetime):
        started_at = started_at.strftime(TIME_FORMAT)

    return os.path.join(dest, f"{started_at}_{cluster['id']}")


def write_metadata_file(client: InventoryClient, cluster: dict, file_name: str):
    d = {'cluster': cluster}

    try:
        d['link'] = f"{get_ui_url_from_api_url(client.inventory_url)}/clusters/{cluster['id']}"
    except KeyError:
        pass

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


def handle_arguments():
    parser = ArgumentParser(description="Download logs")

    parser.add_argument("inventory_url", help="URL of remote inventory", type=str)
    parser.add_argument("dest", help="Destination to download logs", type=str)

    parser.add_argument("--cluster-id", help="Cluster id to download its logs", type=str, default=None, nargs='?')

    return parser.parse_args()


if __name__ == '__main__':
    main()
