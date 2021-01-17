#!/usr/bin/env python3
# pylint: disable=invalid-name,bare-except,missing-function-docstring,too-few-public-methods,missing-class-docstring,missing-module-docstring,line-too-long

import argparse
import logging
import netrc
import os
import json
from urllib.parse import urlparse
import re
from collections import OrderedDict
from collections import defaultdict
from datetime import datetime
import jira
import requests
from tabulate import tabulate
import dateutil.parser

DEFAULT_DAYS_TO_HANDLE = 30

logger = logging.getLogger(__name__)

JIRA_DESCRIPTION = """
h1. Cluster Info

*Cluster ID:* [{cluster_id}|https://cloud.redhat.com/openshift/assisted-installer/clusters/{cluster_id}]
*Username:* {username}
*Created_at:* {created_at}
*Installation started at:* {installation_started_at}
*Failed on:* {failed_on}
*status:* {status}
*status_info:* {status_info}
*OpenShift version:* {openshift_version}

*links:*
* [logs|{logs_url}]
* [Metrics|https://grafana.app-sre.devshift.net/d/assisted-installer-cluster-overview/cluster-overview?orgId=1&from=now-1h&to=now&var-datasource=app-sre-prod-04-prometheus&var-clusterId={cluster_id}]
* [Kibana|https://kibana-openshift-logging.apps.app-sre-prod-04.i5h0.p1.openshiftapps.com/app/kibana#/discover?_g=(refreshInterval:(pause:!t,value:0),time:(from:now-24h,mode:quick,to:now))&_a=(columns:!(_source),interval:auto,query:'{cluster_id}',sort:!('@timestamp',desc))]
* [DM Elastic|http://assisted-elastic.usersys.redhat.com:5601/app/discover#/?_g=(filters:!(),query:(language:kuery,query:''),refreshInterval:(pause:!t,value:0),time:(from:now-2w,to:now))&_a=(columns:!(message,cluster_id),filters:!(),index:'2d6517b0-5432-11eb-8ff7-115676c7222d',interval:auto,query:(language:kuery,query:'cluster_id:%20%22{cluster_id}%22%20'),sort:!())]

h1. Triage Results
h2. Failure Reason:

h2. Comments:

"""


def format_description(failure_data):
    return JIRA_DESCRIPTION.format(**failure_data)

def days_ago(datestr):
    try:
        return (datetime.now() - dateutil.parser.isoparse(datestr)).days
    except:
        logger.debug("Cannot parse date: %s", datestr)
        return 9999

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

    def _update_description(self, key, new_description):
        i = self._jclient.issue(key)
        i.update(fields={"description": new_description})

    @staticmethod
    def _generate_table_for_report(hosts):
        return tabulate(hosts, headers="keys", tablefmt="jira") + "\n"

    @staticmethod
    def _logs_url_to_api(url):
        '''
        the log server has two formats for the url
        - URL for the UI  - http://assisted-logs-collector.usersys.redhat.com/#/2020-10-15_19:10:06_347ce6e8-bb4d-4751-825f-5e92e24da0d9/
        - URL for the API - http://assisted-logs-collector.usersys.redhat.com/files/2020-10-15_19:10:06_347ce6e8-bb4d-4751-825f-5e92e24da0d9/
        This function will return an API URL, regardless of which URL is supplied
        '''
        return re.sub(r'(http://[^/]*/)#(/.*)', r'\1files\2', url)

    @staticmethod
    def _logs_url_to_ui(url):
        '''
        the log server has two formats for the url
        - URL for the UI  - http://assisted-logs-collector.usersys.redhat.com/#/2020-10-15_19:10:06_347ce6e8-bb4d-4751-825f-5e92e24da0d9/
        - URL for the API - http://assisted-logs-collector.usersys.redhat.com/files/2020-10-15_19:10:06_347ce6e8-bb4d-4751-825f-5e92e24da0d9/
        This function will return an UI URL, regardless of which URL is supplied
        '''
        return re.sub(r'(http://[^/]*/)files(/.*)', r'\1#\2', url)

    @staticmethod
    def _get_hostname(host):
        hostname = host.get('requested_hostname')
        if hostname:
            return  hostname

        inventory = json.loads(host['inventory'])
        return inventory['hostname']


class HostsStatusSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Host details:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_to_api(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        cluster = md['cluster']

        hosts = []
        for host in cluster['hosts']:
            info = host['status_info']
            role = host['role']
            if host.get('bootstrap', False):
                role = 'bootstrap'
            hosts.append(OrderedDict(
                id=host['id'],
                hostname=self._get_hostname(host),
                progress=host['progress']['current_stage'],
                status=host['status'],
                role=role,
                status_info=str(info)))

        report = self._generate_table_for_report(hosts)
        self._update_triaging_ticket(issue_key, report, should_update=should_update)


class FailureDescription(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="")

    def build_description(self, url, cluster_md):
        cluster_data = {"cluster_id": cluster_md['id'],
                        "logs_url": self._logs_url_to_ui(url),
                        "openshift_version": cluster_md['openshift_version'],
                        "created_at": format_time(cluster_md['created_at']),
                        "installation_started_at": format_time(cluster_md['install_started_at']),
                        "failed_on": format_time(cluster_md['status_updated_at']),
                        "status": cluster_md['status'],
                        "status_info": cluster_md['status_info'],
                        "username": cluster_md['user_name']}

        return format_description(cluster_data)

    def _update_ticket(self, url, issue_key, should_update=False):

        if not should_update:
            logger.debug("Not updating description of %s", issue_key)
            return

        url = self._logs_url_to_api(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        cluster = md['cluster']

        description = self.build_description(url, cluster)

        logger.info("Updating description of %s", issue_key)
        self._update_description(issue_key, description)


class HostsExtraDetailSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Host extra details:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_to_api(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        cluster = md['cluster']

        hosts = []
        for host in cluster['hosts']:
            inventory = json.loads(host['inventory'])
            hosts.append(OrderedDict(
                id=host['id'],
                hostname=inventory['hostname'],
                requested_hostname=host.get('requested_hostname', ""),
                last_contacted=format_time(host['checked_in_at']),
                installation_disk=host.get('installation_disk_path', ""),
                product_name=inventory['system_vendor']['product_name'],
                manufacturer=inventory['system_vendor']['manufacturer'],
                virtual_host=inventory['system_vendor'].get('virtual', False),
                disks_count=len(inventory['disks'])
            ))

        report = self._generate_table_for_report(hosts)
        self._update_triaging_ticket(issue_key, report, should_update=should_update)


class StorageDetailSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Host storage details:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_to_api(url)
        try:
            md = self._get_metadata_json(url)
        except:
            logger.exception("Error getting logs for %s at %s", issue_key, url)
            return

        cluster = md['cluster']

        hosts = []
        for host in cluster['hosts']:
            inventory = json.loads(host['inventory'])
            disks = inventory['disks']
            disks_details = defaultdict(list)
            for d in disks:
                disks_details['type'].append(d.get('drive_type', ""))
                disks_details['bootable'].append(str(d.get('bootable', "NA")))
                disks_details['name'].append(d.get('name', ""))
                disks_details['path'].append(d.get('path', ""))
                disks_details['by-path'].append(d.get('by_path', ""))
            hosts.append(OrderedDict(
                id=host['id'],
                hostname=self._get_hostname(host),
                disk_name="\n".join(disks_details['name']),
                disk_type="\n".join(disks_details['type']),
                disk_path="\n".join(disks_details['path']),
                disk_bootable="\n".join(disks_details['bootable']),
                disk_by_path="\n".join(disks_details['by-path'])
            ))

        report = self._generate_table_for_report(hosts)
        self._update_triaging_ticket(issue_key, report, should_update=should_update)


class ComponentsVersionSignature(Signature):
    def __init__(self, jira_client):
        super().__init__(jira_client, comment_identifying_string="h1. Components version information:\n")

    def _update_ticket(self, url, issue_key, should_update=False):

        url = self._logs_url_to_api(url)
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

        url = self._logs_url_to_api(url)
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

            if (len(inventory['disks']) == 1 and "KVM" in inventory['system_vendor']['product_name'] and
                    host['progress']['current_stage'] == 'Rebooting' and host['status'] == 'error'):
                if host['role'] == 'bootstrap':
                    return

                hosts.append(OrderedDict(
                    id=host['id'],
                    hostname=self._get_hostname(host),
                    role=host['role'],
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
SIGNATURES = [FailureDescription, ComponentsVersionSignature, HostsStatusSignature, HostsExtraDetailSignature, StorageDetailSignature, LibvirtRebootFlagSignature]

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
LOGS_URL_FROM_DESCRIPTION_OLD = re.compile(r".*logs:\* \[(http.*)\]")
LOGS_URL_FROM_DESCRIPTION_NEW = re.compile(r".*\* \[logs\|(http.*)\]")

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
    m = LOGS_URL_FROM_DESCRIPTION_NEW.search(issue.fields.description)
    if m is None:
        logger.debug("Cannot find new format of URL for logs in %s", issue.key)
        m = LOGS_URL_FROM_DESCRIPTION_OLD.search(issue.fields.description)
        if m is None:
            logger.debug("Cannot find old format of URL for logs in %s", issue.key)
            return None
    return m.groups()[0]

def get_all_triage_tickets(jclient, only_recent=False):
    recent_filter = "" if not only_recent else 'and created >= -31d'
    query = 'project = MGMT AND component = "Assisted-installer Triage" {}'.format(recent_filter)
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

    if not args.issue:
        issues = get_all_triage_tickets(jclient, only_recent=args.recent_issues)
    else:
        issues = [get_issue(jclient, args.issue)]

    for issue in issues:
        url = get_logs_url_from_issue(issue)
        add_signatures(jclient, url, issue.key, should_update=args.update,
                       signatures=args.update_signature)


def format_time(time_str):
    return  dateutil.parser.isoparse(time_str).strftime("%Y-%m-%d %H:%M:%S")


def add_signatures(jclient, url, issue_key, should_update=False, signatures=None):
    name_to_signature = {s.__name__: s for s in SIGNATURES}
    signatures_to_add = SIGNATURES
    if signatures:
        should_update = True
        signatures_to_add = [v for k, v in name_to_signature.items() if k in signatures]

    for sig in signatures_to_add:
        s = sig(jclient)
        s.update_ticket(url, issue_key, should_update=should_update)


if __name__ == "__main__":
    signature_names = [s.__name__ for s in SIGNATURES]
    parser = argparse.ArgumentParser()
    loginGroup = parser.add_argument_group(title="login options")
    loginArgs = loginGroup.add_mutually_exclusive_group()
    loginArgs.add_argument("--netrc", default="~/.netrc", required=False, help="netrc file")
    loginArgs.add_argument("-up", "--user-password", required=False, help="Username and password in the format of user:pass")
    selectorsGroup = parser.add_argument_group(title="Issues selection")
    selectors = selectorsGroup.add_mutually_exclusive_group(required=True)
    selectors.add_argument("-r", "--recent-issues", action='store_true', help="Handle recent (30 days) Triaging Tickets")
    selectors.add_argument("-a", "--all-issues", action='store_true', help="Handle all Triaging Tickets")
    selectors.add_argument("-i", "--issue", required=False, help="Triage issue key")
    parser.add_argument("-u", "--update", action="store_true", help="Update ticket even if signature already exist")
    parser.add_argument("-v", "--verbose", action="store_true", help="Output verbose logging")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Dry run. Don't update tickets")
    parser.add_argument("-us", "--update-signature", action='append', choices=signature_names,
                          help="Update tickets with only the signatures specified")

    args = parser.parse_args()

    logging.basicConfig(level=logging.WARN, format='%(levelname)-10s %(message)s')
    logging.getLogger("__main__").setLevel(logging.INFO)

    if args.verbose:
        logging.getLogger("__main__").setLevel(logging.DEBUG)


    main(args)
