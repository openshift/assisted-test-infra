#!/usr/bin/env python3

# This script gets a list of the filed clusters from the assisted-logs-server
# For each cluster, which does not already has a triaging Jira ticket, it creates one
#

import argparse
import logging
import netrc
import os
import sys
from urllib.parse import urlparse
import requests
import jira
import add_triage_signature


LOGS_COLLECTOR = "http://assisted-logs-collector.usersys.redhat.com"
JIRA_SERVER = "https://issues.redhat.com/"
DEFAULT_NETRC_FILE = "~/.netrc"
JIRA_SUMMARY = "cloud.redhat.com failure: {failure_id}"
JIRA_DESCRIPTION = """
h1. Cluster Info

*Cluster ID:* [{cluster_id}|https://cloud.redhat.com/openshift/assisted-installer/clusters/{cluster_id}]
*Username:* {username}
*created_at:* {created_at}
*Failed on:* {failed_on}
*status:* {status}
*status_info:* {status_info}
*OpenShift version:* {openshift_version}

*logs:* [{logs_collector}/#/{failure_id}/]

h1. Triage Results
h2. Failure Reason:

h2. Comments:

"""



def get_credentials_from_netrc(server, netrc_file=DEFAULT_NETRC_FILE):
    cred = netrc.netrc(os.path.expanduser(netrc_file))
    username, _, password = cred.authenticators(server)
    return username, password


def get_jira_client(username, password):
    logger.info("log-in with username: %s", username)
    return jira.JIRA(JIRA_SERVER, basic_auth=(username, password))


def format_description(failure_data):
    return JIRA_DESCRIPTION.format(logs_collector=LOGS_COLLECTOR, **failure_data)

def format_summary(failure_data):
    return JIRA_SUMMARY.format(**failure_data)

def format_labels(failure_data):
    return ["no-qe",
            "AI_CLOUD_TRIAGE",
            "AI_CLUSTER_{cluster_id}".format(**failure_data),
            "AI_USER_{username}".format(**failure_data)]


def get_all_triage_tickets(jclient):
    query = 'component = "Assisted-Installer Triage"'
    idx = 0
    block_size = 100
    issues = []
    while True:
        i = jclient.search_issues(query, maxResults=block_size, startAt=idx, fields=['summary', 'key'])
        if len(i) == 0:
            break
        #for x in i:
        #    print("{} - {}".format(x.key, x.fields.summary))
        issues.extend([x.fields.summary for x in i])
        idx += block_size

    return set(issues)


def create_jira_ticket(jclient, existing_tickets, failure_data):
    summary = format_summary(failure_data)
    if summary in existing_tickets:
        logger.debug("issue found: %s", summary)
        return None

    new_issue = jclient.create_issue(project="MGMT",
                                     summary=summary,
                                     components=[{'name': "Assisted-installer Triage"}],
                                     priority={'name': 'Blocker'},
                                     issuetype={'name': 'Bug'},
                                     labels=format_labels(failure_data),
                                     description=format_description(failure_data))
    logger.info("issue created: %s", new_issue)
    return new_issue


def main(arg):
    if arg.user_password is None:
        username, password = get_credentials_from_netrc(urlparse(JIRA_SERVER).hostname, arg.netrc)
    else:
        try:
            [username, password] = arg.user_password.split(":", 1)
        except:
            logger.error("Failed to parse user:password")

    jclient = get_jira_client(username, password)

    try:
        res = requests.get("{}/files/".format(LOGS_COLLECTOR))
    except Exception:
        logger.exception("Error getting list of failed clusters")
        sys.exit(1)

    res.raise_for_status()
    failed_clusters = res.json()

    existing_tickets = get_all_triage_tickets(jclient)

    for failure in failed_clusters:
        #print("cluster: {}".format(failure["name"]))
        res = requests.get("{}/files/{}/metdata.json".format(LOGS_COLLECTOR, failure['name']))
        res.raise_for_status()
        cluster = res.json()['cluster']

        if cluster['status'] == "error":
            cluster_data = {"cluster_id": cluster['id'],
                            "failure_id": failure['name'],
                            "openshift_version": cluster['openshift_version'],
                            "created_at": cluster['created_at'],
                            "failed_on": cluster['status_updated_at'],
                            "status": cluster['status'],
                            "status_info": cluster['status_info'],
                            "username": cluster['user_name']}
            new_issue = create_jira_ticket(jclient, existing_tickets, cluster_data)
            if new_issue is not None:
                logs_url = "{}/files/{}".format(LOGS_COLLECTOR, failure['name'])
                add_triage_signature.add_signatures(jclient, logs_url, new_issue.key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    loginGroup = parser.add_argument_group(title="login options")
    loginArgs = loginGroup.add_mutually_exclusive_group()
    loginArgs.add_argument("--netrc", default="~/.netrc", required=False, help="netrc file")
    loginArgs.add_argument("-up", "--user-password", required=False, help="Username and password in the format of user:pass")
    parser.add_argument("-v", "--verbose", action="store_true", help="Output verbose logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARN, format='%(levelname)-10s %(message)s')
    logger = logging.getLogger(__name__)
    logging.getLogger("__main__").setLevel(logging.INFO)

    if args.verbose:
        logging.getLogger("__main__").setLevel(logging.DEBUG)

    main(args)
