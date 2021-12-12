import json
from argparse import ArgumentParser
from collections import Counter

from assisted_test_infra.download_logs import gather_sosreport_data
from assisted_test_infra.download_logs.download_logs import download_cluster_logs, get_clusters, should_download_logs
from assisted_test_infra.test_infra.assisted_service_api import ClientFactory
from assisted_test_infra.test_infra.utils import get_env, log

CONNECTION_TIMEOUT = 30


def main():
    args = handle_arguments()

    if args.sosreport:
        gather_sosreport_data(output_dir=args.dest)

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
            pull_secret=args.pull_secret,
        )
    else:
        clusters = get_clusters(client, args.download_all)

        if not clusters:
            log.info("No clusters were found")
            return

        for cluster in clusters:
            if args.download_all or should_download_logs(cluster):
                download_cluster_logs(
                    client, cluster, args.dest, args.must_gather, args.update_by_events, pull_secret=args.pull_secret
                )

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

    return parser.parse_args()


if __name__ == "__main__":
    main()
