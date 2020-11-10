#!/usr/bin/env python3

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
import dateutil.parser


logger = logging.getLogger(__name__)


############################
# Common functionality
############################
class Signature:
    is_dry_run = False
    def __init__(self, jira_client, comment_identifying_string):
        self._jclient = jira_client
        self._identifing_string = comment_identifying_string

    def update_ticket(self, url, issue_key, should_update=False):
        try:
            self._update_ticket(url, issue_key, should_update=should_update)
        except:
            logger.exception("error updating ticket")

    def _update_ticket(self, url, issue_key, should_update=False):
        raise NotImplementedError

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
        signature_name = type(self).__name__
        if self.is_dry_run:
            print(report)
            return

        if jira_comment is None:
            logger.info("Adding new '%s' comment to %s", signature_name, key)
            self._jclient.add_comment(key, report)
        elif should_update:
            logger.info("Updating existing '%s' comment of %s", signature_name, key)
            jira_comment.update(body=report)
        else:
            logger.debug("Not updating existing '%s' comment of %s", signature_name, key)

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

    @staticmethod
    def _format_time(time_str):
        return  dateutil.parser.isoparse(time_str).strftime("%Y-%m-%d %H:%M:%S")


class HostsStatusSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Host details:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

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
            hostname = host.get('requested_hostname')
            if hostname is None:
                hostname = inventory['hostname']
            hosts.append(OrderedDict(
                id=host['id'],
                hostname=hostname,
                progress=host['progress']['current_stage'],
                status=host['status'],
                role=role,
                status_info=str(info)))

        report = self._generate_table_for_report(hosts)
        self._update_triaging_ticket(issue_key, report, should_update=should_update)


class HostsExtraDetailSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Host extra details:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

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
            requested_hostname = host.get('requested_hostname', "")
            hostname = inventory['hostname']
            hosts.append(OrderedDict(
                id=host['id'],
                hostname=inventory['hostname'],
                requested_hostname=host.get('requested_hostname', ""),
                last_contacted=self._format_time(host['checked_in_at']),
                installation_disk=host.get('installation_disk_path', ""),
                product_name=inventory['system_vendor']['product_name'],
                manufacturer=inventory['system_vendor']['manufacturer'],
                disks_count=len(inventory['disks'])
            ))

        report = self._generate_table_for_report(hosts)
        self._update_triaging_ticket(issue_key, report, should_update=should_update)


class ComponentsVersionSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Components version information:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_fixup(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        report = ""
        release_tag = md.get('release_tag')
        if release_tag:
            report = "Release tag: {}\n".format(release_tag)

        versions = md.get('versions')
        if versions:
            report += "assisted-installer: {}\n".format(versions['assisted-installer'])
            report += "assisted-installer-controller: {}\n".format(versions['assisted-installer-controller'])
            report += "assisted-installer-agent: {}\n".format(versions['discovery-agent'])

        if report != "":
            self._update_triaging_ticket(issue_key, report, should_update=should_update)


class LibvirtRebootFlagSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Potential hosts with libvirt _on_reboot_ flag issue (MGMT-2840):\n")

    def _update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_fixup(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        cluster = md['cluster']

        # this signature is relevant only if all hosts, but the bootstrap is in 'Rebooting' stage
        hosts = []
        for host in cluster['hosts']:
            inventory = json.loads(host['inventory'])
            requested_hostname = host.get('requested_hostname', "")
            hostname = inventory['disks']

            if (len(inventory['disks']) == 1 and "KVM" in inventory['system_vendor']['product_name'] and
                host['progress']['current_stage'] == 'Rebooting' and host['status'] == 'error'):
                if host['role'] == 'bootstrap':
                    return

                hosts.append(OrderedDict(
                    id=host['id'],
                    hostname=inventory['hostname'],
                    role = host['role'],
                    progress=host['progress']['current_stage'],
                    status=host['status'],
                    num_disks=len(inventory.get('disks', []))))

        if len(hosts)+1 == len(cluster['hosts']):
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


def get_jira_client(username, password):
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
    if args.user_password is None:
        username, password = get_credentials_from_netrc(urlparse(JIRA_SERVER).hostname, args.netrc)
    else:
        try:
            [username, password] = args.user_password.split(":", 1)
        except:
            logger.error("Failed to parse user:password")

    jclient = get_jira_client(username, password)

    if args.dry_run:
        Signature.is_dry_run = True

    if args.all_issues:
        issues = get_all_triage_tickets(jclient)
    else:
        issues = [get_issue(jclient, args.issue)]

    for issue in issues:
        url = get_logs_url_from_issue(issue)
        add_signatures(jclient, url, issue.key, should_update=args.update)


def add_signatures(jclient, url, issue_key, should_update=False):
    signatures = [ComponentsVersionSignature, HostsStatusSignature, HostsExtraDetailSignature, LibvirtRebootFlagSignature]

    for sig in signatures:
        s = sig(jclient)
        s.update_ticket(url, issue_key, should_update=should_update)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    loginGroup = parser.add_argument_group(title="login options")
    loginArgs = loginGroup.add_mutually_exclusive_group()
    loginArgs.add_argument("--netrc", default="~/.netrc", required=False, help="netrc file")
    loginArgs.add_argument("-up", "--user-password", required=False, help="Username and password in the format of user:pass")
    selectorsGroup = parser.add_argument_group(title="Issues selection")
    selectors = selectorsGroup.add_mutually_exclusive_group(required=True)
    selectors.add_argument("-a", "--all_issues", action='store_true', help="Search query to use")
    selectors.add_argument("-i", "--issue", required=False, help="Triage issue key")
    parser.add_argument("-u", "--update", action="store_true", help="Update ticket even if comment already exist")
    parser.add_argument("-v", "--verbose", action="store_true", help="Output verbose logging")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Dry run. Don't update tickets")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARN, format='%(levelname)-10s %(message)s')
    logging.getLogger("__main__").setLevel(logging.INFO)

    if args.verbose:
        logging.getLogger("__main__").setLevel(logging.DEBUG)


    main(args)
