#!/usr/bin/env python3

import re
import os
import time
import json
import random
import urllib3
import logging
import hashlib
import tempfile
import contextlib
import elasticsearch

from logger import log
from monitoring import process
from contextlib import suppress
from argparse import ArgumentParser
from test_infra.assisted_service_api import ClientFactory

import assisted_service_client

from test_infra import warn_deprecate

warn_deprecate()

RETRY_INTERVAL = 60 * 5
MAX_EVENTS = 5000

UUID_REGEX = r'[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}'

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)

class ScrapeEvents:
    def __init__(self, inventory_url: str, offline_token: str, index: str, es_server: str, es_user:str, es_pass:str, backup_destination: str):

        self.inventory_url = inventory_url
        self.client = ClientFactory.create_client(url=self.inventory_url, offline_token=offline_token)

        self.index = index
        self.es = elasticsearch.Elasticsearch(es_server, http_auth=(es_user, es_pass))

        self.backup_destination = backup_destination
        if self.backup_destination and not os.path.exists(self.backup_destination):
            os.makedirs(self.backup_destination)

        self.cache_event_count_per_cluster = dict()

    def run_service(self):

        while True:
            clusters = self.get_clusters()
            random.shuffle(clusters)

            if not clusters:
                log.warn(f'No clusters were found, waiting {RETRY_INTERVAL/60} min')
                time.sleep(RETRY_INTERVAL)
                break

            cluster_count = len(clusters)
            for i, cluster in enumerate(clusters):
                cluster_id = cluster["id"]
                log.info(f"{i}/{cluster_count}: Starting process of cluster {cluster_id}")
                if "hosts" not in cluster or len(cluster["hosts"]) == 0:
                    cluster["hosts"] = self.client.get_cluster_hosts(cluster_id=cluster["id"])

                self.process_cluster(cluster)

    def get_metadata_json(self, cluster: dict):
        d = {'cluster': cluster}
        d.update(self.client.get_versions())
        return d

    def process_cluster(self, cluster):
        with tempfile.NamedTemporaryFile() as temp_event_file:
            self.write_events_file(cluster, temp_event_file.name)
            with open(temp_event_file.name) as f:
                event_list = json.load(f)

        self.elastefy_events(cluster, event_list)

    def elastefy_events(self, cluster, event_list):

        cluster_id = cluster["id"]

        event_count = len(event_list)
        if event_count > MAX_EVENTS:
            log.info(f"Cluster {cluster_id} has {event_count} event records, logging only {MAX_EVENTS}")
            event_list = event_list[:MAX_EVENTS]

        metadata_json = self.get_metadata_json(cluster)

        if self.backup_destination:
            self.save_new_backup(cluster_id, event_list, metadata_json)

        cluster_bash_data = process_metadata(metadata_json)
        event_names = get_cluster_object_names(cluster_bash_data)

        self.process_and_log_events(cluster_bash_data, event_list, event_names)


        if self.does_cluster_needs_full_update(cluster_id, event_list):
            log.info(f"Cluster {cluster_id} logged events are not same as the event count, logging all clusters events")
            self.process_and_log_events(cluster_bash_data, event_list, event_names, False)

    def does_cluster_needs_full_update(self, cluster_id, event_list):
        # check if cluster is missing past events
        cluster_events_count = self.cache_event_count_per_cluster.get(cluster_id, None)
        relevant_event_count = len([event for event in event_list if not process.is_event_skippable(event)])

        if cluster_events_count and cluster_events_count == relevant_event_count:
            return False
        else:
            cluster_events_count_from_db = self.get_cluster_event_count_on_es_db(cluster_id)
            self.cache_event_count_per_cluster[cluster_id] = cluster_events_count_from_db
        if cluster_events_count_from_db < relevant_event_count:
            missing_events = relevant_event_count - cluster_events_count_from_db
            logging.info(f"cluster {cluster_id} is missing {missing_events} events")
            return True
        else:
            return False

    def get_cluster_event_count_on_es_db(self, cluster_id):
        time.sleep(1)
        return self.es.search(index=self.index,
                              body={"query": {"match_phrase": {"cluster.id": cluster_id}}})["hits"]["total"]["value"]

    def process_and_log_events(self, cluster_bash_data, event_list, event_names, only_new_events=True):
        for event in event_list[::-1]:
            if process.is_event_skippable(event):
                continue

            doc_id = get_doc_id(event)
            cluster_bash_data["no_name_message"] = get_no_name_message(event["message"], event_names)
            cluster_bash_data["inventory_url"] = self.inventory_url

            if "props" in event:
                event["event.props"] = json.loads(event["props"])

            process_event_doc(event, cluster_bash_data)
            ret = self.log_doc(cluster_bash_data, doc_id)

            for key in event:
                _ = cluster_bash_data.pop(key,None)

            if not ret and only_new_events:
                break

    def save_new_backup(self,cluster_id, event_list, metadata_json):
        cluster_backup_directory_path = os.path.join(self.backup_destination, f"cluster_{cluster_id}")
        if not os.path.exists(cluster_backup_directory_path):
            os.makedirs(cluster_backup_directory_path)

        event_dest = os.path.join(cluster_backup_directory_path, "events.json")
        with open(event_dest, "w") as f:
            json.dump(event_list, f, indent=4)

        metadata_dest = os.path.join(cluster_backup_directory_path, "metadata.json")
        with open(metadata_dest, "w") as f:
            json.dump(metadata_json, f, indent=4)

    def log_doc(self, doc, id_):
        try:
            res = self.es.create(index=self.index, body=doc, id=id_)
        except elasticsearch.exceptions.ConflictError:
            log.debug("Hit logged event")
            return None
        return res

    def write_events_file(self, cluster, output_file):
        with suppress(assisted_service_client.rest.ApiException):
            self.client.download_cluster_events(cluster['id'], output_file, categories=["user", "metrics"])

    def get_clusters(self):
        return self.client.clusters_list()

def get_no_name_message(event_message: str, event_names: list):
    event_message = re.sub(r"^Host \S+:", "", event_message)
    for name in event_names:
        event_message = event_message.replace(name, "Name")
    event_message = re.sub(UUID_REGEX, "UUID", event_message)
    return event_message

def get_cluster_object_names(cluster_bash_data):
    strings_to_remove = list()
    for host in cluster_bash_data["cluster"]["hosts"]:
        host_name = host.get("requested_hostname", None)
        if host_name:
            strings_to_remove.append(host_name)
    strings_to_remove.append(cluster_bash_data["cluster"]["name"])
    return strings_to_remove

def process_metadata(metadata_json):
    p = process.GetProcessedMetadataJson(metadata_json)
    return p.get_processed_json()

def get_doc_id(event_json):
    id_str = event_json["event_time"] + event_json["cluster_id"] + event_json["message"]
    _id = int(hashlib.md5(id_str.encode('utf-8')).hexdigest(), 16)
    return str(_id)

def process_event_doc(event_data, cluster_bash_data):
    cluster_bash_data.update(event_data)



def handle_arguments():
    parser = ArgumentParser(description="Elastify events")
    parser.add_argument("--inventory-url", help="URL of remote inventory", type=str)
    parser.add_argument("--offline-token", help="offline token", type=str)
    parser.add_argument("-es", "--es_server", help="Elasticsearch server", type=str)
    parser.add_argument("-eu", "--es_user", help="Elasticsearch user", type=str)
    parser.add_argument("-ep", "--es_pass", help="Elasticsearch password", type=str)
    parser.add_argument("--index", help="Index", type=str)
    parser.add_argument("--backup-destination", help="Path to save backup, if empty no back up saved", default=None, type=str)

    return parser.parse_args()

def main():
    args = handle_arguments()

    while True:
        try:
            scrape_events = ScrapeEvents(inventory_url=args.inventory_url,
                                         offline_token=args.offline_token,
                                         index=args.index,
                                         es_server=args.es_server,
                                         es_user = args.es_user,
                                         es_pass = args.es_pass,
                                         backup_destination=args.backup_destination)
            scrape_events.run_service()
        except Exception as EX:
            log.warn(f"Elastefying logs failed with error {EX}, sleeping for {RETRY_INTERVAL} and retrying")
            time.sleep(RETRY_INTERVAL)

if __name__ == '__main__':
    main()
