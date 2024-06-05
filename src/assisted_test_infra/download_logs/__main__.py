import json
import os
from argparse import ArgumentParser
from collections import Counter

from kubernetes.client import CustomObjectsApi

from assisted_test_infra.download_logs import gather_sosreport_data
from assisted_test_infra.download_logs.download_logs import (
    download_cluster_logs,
    download_logs_kube_api,
    get_clusters,
    should_download_logs,
)
from assisted_test_infra.test_infra.helper_classes.kube_helpers import ClusterDeployment
from assisted_test_infra.test_infra.utils import get_env
from service_client import ClientFactory, log
from tests.config import global_variables

CONNECTION_TIMEOUT = 30


def kube_api_logs(args):
    client = ClientFactory.create_kube_api_client(args.kubeconfig_path)
    for item in ClusterDeployment.list_all_namespaces(CustomObjectsApi(client)).get("items", []):
        if item["spec"]["clusterName"]:
            download_logs_kube_api(
                client,
                item["spec"]["clusterName"],
                item["metadata"]["namespace"],
                args.dest,
                args.must_gather,
                args.kubeconfig_path,
            )


def main():
    args = handle_arguments()

    if args.sosreport:
        log.info("Sos report")
        gather_sosreport_data(output_dir=args.dest)

    if global_variables.is_kube_api:
        log.info("download logs on kube api flow")
        return kube_api_logs(args)

    client = ClientFactory.create_client(
        url=args.inventory_url, timeout=CONNECTION_TIMEOUT, offline_token=get_env("OFFLINE_TOKEN")
    )
    if args.cluster_id:
        cluster = client.cluster_get(args.cluster_id)
        download_cluster_logs(
            client,
            json.loads(json.dumps(cluster.to_dict(), sort_keys=True, default=str)),
            args.dest,
            args.must_gather,
            args.update_by_events,
        )
    else:
        clusters = get_clusters(client, args.download_all)

        if not clusters:
            log.info("No clusters were found")
            return

        for cluster in clusters:
            if args.download_all or should_download_logs(cluster):
                download_cluster_logs(client, cluster, args.dest, args.must_gather, args.update_by_events)

        log.info("Cluster installation statuses: %s", dict(Counter(cluster["status"] for cluster in clusters).items()))


def handle_arguments():
    parser = ArgumentParser(description="Download logs")

    parser.add_argument("inventory_url", help="URL of remote inventory", type=str)
    parser.add_argument("dest", help="Destination to download logs", type=str)
    parser.add_argument("--cluster-id", help="Cluster id to download its logs", type=str, default=None, nargs="?")
    parser.add_argument("--download-all", help="Download logs from all clusters", action="store_true")
    parser.add_argument("--must-gather", help="must-gather logs", action="store_true")
    parser.add_argument("--sosreport", help="gather sosreport from each node", action="store_true")
    parser.add_argument("--update-by-events", help="Update logs if cluster events were updated", action="store_true")
    parser.add_argument("-ps", "--pull-secret", help="Pull secret", type=str, default="")
    parser.add_argument(
        "-kp",
        "--kubeconfig-path",
        help="kubeconfig-path",
        type=str,
        default=os.path.join(os.getenv("HOME"), ".kube/config"),
    )

    return parser.parse_args()


if __name__ == "__main__":
    main()
