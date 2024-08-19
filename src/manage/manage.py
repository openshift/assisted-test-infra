#!/usr/bin/env python3

import sys
from argparse import ArgumentParser
from datetime import datetime

import urllib3
import yaml
from assisted_service_client.rest import ApiException

from deprecated_utils import warn_deprecate
from service_client import ClientFactory, ServiceAccount, log

warn_deprecate()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

description = (
    """Manage an assisted-service deployment by directly run manage types described on manageable_options.yaml"""
)


class Manage:
    def __init__(self, inventory_url: str, type: str, offline_token: str, service_account: ServiceAccount):
        self.client = ClientFactory.create_client(
            url=inventory_url, offline_token=offline_token, service_account=service_account
        )

        with open("src/manage/manageable_options.yaml", "r") as f:
            options = yaml.load(f, Loader=yaml.FullLoader)

        manage_config = options.get(type, None)

        if not manage_config:
            raise ValueError(f"{type} is not a valid manageable_options option")

        days_back = manage_config["days_back"]
        measure_field = manage_config["measure_field"]

        clusters = self.get_clusters()
        clusters_to_process = list()

        for cluster in clusters:
            if is_older_then(cluster[measure_field], days_back):
                clusters_to_process.append(cluster["id"])

        len_of_clusters_to_prcess = len(clusters_to_process)

        log.info(f"Running {type} of {len_of_clusters_to_prcess} clusters")

        if not query_yes_no():
            return

        method = getattr(self.client, manage_config["method"])

        for cluster_id in clusters_to_process:
            try:
                method(cluster_id=cluster_id)
            except ApiException as e:
                log.warning(f"Can't process cluster_id={cluster_id}, {e}")

    def get_clusters(self):
        return self.client.get_all_clusters()


def is_older_then(date: str, days: int):
    date_time = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
    return (date_time - datetime.now()).days < -days


def query_yes_no(question="Do you want to proceed?", default="yes"):
    valid = {"yes": True, "y": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError(f"invalid default answer: '{default}'")

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


def handle_arguments():
    parser = ArgumentParser(description=description)
    parser.add_argument("--inventory-url", help="URL of remote inventory", type=str)
    parser.add_argument("--offline-token", help="offline token", type=str)
    parser.add_argument(
        "--service-account-client-id",
        help="client ID of the service account used to authenticate against assisted-service",
        type=str,
    )
    parser.add_argument(
        "--service-account-client-secret",
        help="client secret of the service account used to authenticate against assisted-service",
        type=str,
    )
    parser.add_argument("--type", help="Type of managing process to commit", type=str)

    return parser.parse_args()


def main():
    args = handle_arguments()
    Manage(
        inventory_url=args.inventory_url,
        type=args.type,
        offline_token=args.offline_token,
        service_account=ServiceAccount(
            client_id=args.service_account_client_id, client_secret=args.service_account_client_secret
        ),
    )


if __name__ == "__main__":
    main()
