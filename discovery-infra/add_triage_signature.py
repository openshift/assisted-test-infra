#!/bin/env python

import argparse
import logging
import netrc
import os
import json
from urllib.parse import urlparse
import re
from collections import OrderedDict
import jira
import requests
from tabulate import tabulate


logger = logging.getLogger(__name__)


############################
# Common functionality
############################
class Signature:
    def __init__(self, jira_client, comment_identifying_string):
        self._jclient = jira_client
        self._identifing_string = comment_identifying_string

    @staticmethod
    def _get_metadata_json(cluster_url):
        res = requests.get("{}/metdata.json".format(cluster_url))
        res.raise_for_status()
        return res.json()

    def _find_signature_comment(self, key):
        comments = self._jclient.comments(key)
        for comment in comments:
            if self._identifing_string in comment.body:
                return comment
        return None

    def _update_triaging_ticket(self, key, comment, should_update=False):
        report = "\n"
        report += self._identifing_string
        report += comment
        jira_comment = self._find_signature_comment(key)
        if jira_comment is None:
            logger.info("Adding new comment to %s", key)
            self._jclient.add_comment(key, report)
        elif should_update:
            logger.info("Updating existing comment of %s", key)
            jira_comment.update(body=report)
        else:
            logger.debug("Not updating existing comment of %s", key)

    @staticmethod
    def _generate_table_for_report(hosts):
        return tabulate(hosts, headers="keys", tablefmt="jira") + "\n"

    @staticmethod
    def _logs_url_fixup(url):
        '''
        the log server has two formats for the url
        - URL for the UI  - http://assisted-logs-collector.usersys.redhat.com/#/2020-10-15_19:10:06_347ce6e8-bb4d-4751-825f-5e92e24da0d9/
        - URL for the API - http://assisted-logs-collector.usersys.redhat.com/files/2020-10-15_19:10:06_347ce6e8-bb4d-4751-825f-5e92e24da0d9/
        This function will return an API URL, regardless of which URL is supplied
        '''
        return re.sub(r'(http://[^/]*/)#(/.*)', r'\1files\2', url)


class HostsStatusSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Host details:\n")

    def update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_fixup(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        cluster = md['cluster']

        hosts = []
        for host in cluster['hosts']:
            inventory = json.loads(host['inventory'])
            info = host['status_info']
            role = host['role']
            if host.get('bootstrap', False):
                role = 'bootstrap'
            hosts.append(OrderedDict(
                id=host['id'],
                hostname=inventory['hostname'],
                progress=host['progress']['current_stage'],
                status=host['status'],
                role=role,
                status_info=str(info)))

        report = self._generate_table_for_report(hosts)
        self._update_triaging_ticket(issue_key, report, should_update=should_update)


############################
# Common functionality
############################
DEFAULT_NETRC_FILE = "~/.netrc"
JIRA_SERVER = "https://issues.redhat.com/"

def get_credentials_from_netrc(server, netrc_file=DEFAULT_NETRC_FILE):
    cred = netrc.netrc(os.path.expanduser(netrc_file))
    username, _, password = cred.authenticators(server)
    return username, password


def get_jira_client(netrc_file=DEFAULT_NETRC_FILE):
    username, password = get_credentials_from_netrc(urlparse(JIRA_SERVER).hostname, netrc_file)
    logger.info("log-in with username: %s", username)
    return jira.JIRA(JIRA_SERVER, basic_auth=(username, password))


############################
# Signature runner functionality
############################
LOGS_URL_FROM_DESCRIPTION = re.compile(r".*logs:\* \[(http.*)\]")

def get_issue(jclient, issue_key):
    issue = None
    try:
        issue = jclient.issue(issue_key)
    except jira.exceptions.JIRAError as e:
        if e.status_code != 404:
            raise
    if issue is None or issue.fields.components[0].name != "Assisted-installer Triage":
        raise Exception("issue {} does not exist or is not a triaging issue".format(issue_key))

    return issue


def get_logs_url_from_issue(issue):
    m = LOGS_URL_FROM_DESCRIPTION.search(issue.fields.description)
    if m is None:
        logger.error("Cannot find URL for logs in %s", issue.key)
        return None
    return m.groups()[0]

def get_all_triage_tickets(jclient):
    query = 'component = "Assisted-Installer Triage"'
    idx = 0
    block_size = 100
    issues = []
    while True:
        i = jclient.search_issues(query, maxResults=block_size, startAt=idx)
        if len(i) == 0:
            break
        issues.extend(i)
        idx += block_size

    return issues


def main(args):
    jclient = get_jira_client()

    if args.all_issues:
        issues = get_all_triage_tickets(jclient)
    else:
        issues = [get_issue(jclient, args.issue)]

    for issue in issues:
        url = get_logs_url_from_issue(issue)
        s = HostsStatusSignature(jclient)
        s.update_ticket(url, issue.key, should_update=args.update)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--netrc", default=DEFAULT_NETRC_FILE, help="netrc file")
    selectorsGroup = parser.add_argument_group(title="Issues selection")
    selectors = selectorsGroup.add_mutually_exclusive_group(required=True)
    selectors.add_argument("-a", "--all_issues", action='store_true', help="Search query to use")
    selectors.add_argument("-i", "--issue", required=False, help="Triage issue key")
    parser.add_argument("-u", "--update", action="store_true", help="Update ticket even if comment already exist")
    parser.add_argument("-v", "--verbose", action="store_true", help="Output verbose logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARN, format='%(levelname)-10s %(message)s')
    logging.getLogger("__main__").setLevel(logging.INFO)

    if args.verbose:
        logging.getLogger("__main__").setLevel(logging.DEBUG)


    main(args)
