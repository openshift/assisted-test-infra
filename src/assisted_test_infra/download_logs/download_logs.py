#!/usr/bin/env python3

import filecmp
import json
import os
import shutil
import tarfile
import tempfile
import time
from contextlib import suppress
from datetime import datetime
from operator import itemgetter
from pathlib import Path

import assisted_service_client
import jinja2
import requests
import urllib3
from assisted_service_client import ApiClient
from dateutil.parser import isoparse
from junit_report import JunitTestCase, JunitTestSuite
from paramiko.ssh_exception import SSHException
from scp import SCPException

from assisted_test_infra.test_infra.controllers.node_controllers.libvirt_controller import LibvirtController
from assisted_test_infra.test_infra.controllers.node_controllers.node import Node
from assisted_test_infra.test_infra.controllers.node_controllers.nutanix_controller import NutanixController
from assisted_test_infra.test_infra.controllers.node_controllers.vsphere_controller import VSphereController
from assisted_test_infra.test_infra.helper_classes.hypershift import HyperShift
from assisted_test_infra.test_infra.helper_classes.kube_helpers import AgentClusterInstall, ClusterDeployment
from assisted_test_infra.test_infra.tools.concurrently import run_concurrently
from assisted_test_infra.test_infra.utils import (
    are_host_progress_in_stage,
    config_etc_hosts,
    fetch_url,
    is_cidr_is_ipv4,
    recreate_folder,
    run_command,
    verify_logs_uploaded,
)
from assisted_test_infra.test_infra.utils.kubeapi_utils import get_ip_for_single_node
from consts import CensoredConfig, ClusterStatus, HostsProgressStages, env_defaults
from service_client import InventoryClient, SuppressAndLog, log
from tests.config import ClusterConfig, TerraformConfig

private_ssh_key_path_default = os.path.join(os.getcwd(), str(env_defaults.DEFAULT_SSH_PRIVATE_KEY_PATH))

TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
MAX_RETRIES = 3
MUST_GATHER_MAX_RETRIES = 15
RETRY_INTERVAL = 5  # seconds
SOSREPORT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "man_sosreport.sh")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def censor_sensitive_sources(json_path: str):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        log.debug(f"File {json_path} loaded, keys: {list(data.keys())}")
    except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
        log.warning(f"Failed to load or parse {json_path}: {e}")
        return

    changes_made = False
    filename = os.path.basename(json_path)

    if filename == "bootstrap.ign":
        changes_made |= _censor_storage_files(data)
    else:
        changes_made |= _censor_tls_certificate_authorities(data)

    if changes_made:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _censor_storage_files(data: dict) -> bool:
    changes_made = False
    files = data.get("storage", {}).get("files", [])
    for file_entry in files:
        path = file_entry.get("path", "")
        if path.endswith(CensoredConfig.SENSITIVE_EXTENSIONS) or path in CensoredConfig.EXACT_PATHS:
            if (
                "contents" in file_entry
                and "source" in file_entry["contents"]
                and file_entry["contents"]["source"] != "censored"
            ):
                file_entry["contents"]["source"] = "censored"
                changes_made = True
                log.debug(f"Censored file source for path: {path}")
    return changes_made


def _censor_tls_certificate_authorities(data: dict) -> bool:
    try:
        ca_list = data["ignition"]["security"]["tls"]["certificateAuthorities"]
        if isinstance(ca_list, list) and ca_list:
            if not (len(ca_list) == 1 and ca_list[0].get("source") == "censored"):
                data["ignition"]["security"]["tls"]["certificateAuthorities"] = [
                    {"source": "censored", "verification": {}}
                ]
                log.debug("Censored certificate authorities")
                return True
    except KeyError:
        pass
    return False


def download_cluster_logs(
    client: InventoryClient,
    cluster: dict,
    dest: str,
    must_gather: bool,
    update_by_events: bool = False,
    retry_interval: int = RETRY_INTERVAL,
):
    @JunitTestSuite(custom_filename=f"junit_download_report_{cluster['id']}")
    def download_logs_suite():
        return download_logs(client, cluster, dest, must_gather, update_by_events, retry_interval)

    return download_logs_suite()


@JunitTestCase()
def get_clusters(client, all_cluster):
    if all_cluster:
        return client.get_all_clusters()

    return client.clusters_list()


def should_download_logs(cluster: dict):
    return cluster["status"] in [ClusterStatus.ERROR] or "degraded" in cluster["status_info"]


def get_cluster_installation_date_and_id(cluster: dict) -> tuple[str, str]:
    return (cluster["created_at"][:10], cluster["id"])


def min_number_of_log_files(cluster, is_controller_expected):
    if is_controller_expected:
        return len(cluster["hosts"]) + 1

    return len(cluster["hosts"])


def is_update_needed(output_folder: str, update_on_events_update: bool, client: InventoryClient, cluster: dict):
    if not os.path.isdir(output_folder):
        return True

    # if the logs info in the cluster metadata isn't set to final status we should update
    cluster_md = get_cluster_metadata(output_folder)
    if cluster_md.get("cluster", {}).get("logs_info", "") not in ("timeout", "completed", ""):
        log.info("update needed, missing must-gather logs")
        return True

    if not update_on_events_update:
        return False

    destination_event_file_path = get_cluster_events_path(cluster, output_folder)
    with tempfile.NamedTemporaryFile() as latest_event_tp:
        with SuppressAndLog(assisted_service_client.rest.ApiException):
            client.download_cluster_events(cluster["id"], latest_event_tp.name)

        if filecmp.cmp(destination_event_file_path, latest_event_tp.name):
            log.info(f"no new events found for {destination_event_file_path}")
            return False

        log.info(f"update needed, new events found, deleting {destination_event_file_path}")
        os.remove(destination_event_file_path)
        return True


def download_manifests(client: InventoryClient, cluster_id: str, output_folder: str) -> None:
    manifests_path = os.path.join(output_folder, "cluster_files", "manifests")
    recreate_folder(manifests_path)
    client.download_manifests(cluster_id, manifests_path)


def merge_events(event_paths: list[str]) -> str:
    events = []

    for event_path in event_paths:
        with open(event_path, "rt") as event_file:
            events.extend(json.loads(event_file.read()))

    return json.dumps(sorted(events, key=itemgetter("event_time")))


def gather_event_files(client: InventoryClient, cluster: dict, infra_envs: list[dict], output_folder: str):
    log.info("Gathering event files")
    event_files = []
    for infra_env in infra_envs:
        with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
            infraenv_events = get_infraenv_events_path(infra_env["id"], output_folder)
            client.download_infraenv_events(infra_env["id"], infraenv_events)
            event_files.append(infraenv_events)

    with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
        cluster_events = get_cluster_events_path(cluster, output_folder)
        client.download_cluster_events(cluster["id"], cluster_events)
        event_files.append(cluster_events)

    log.debug("Generating events.html as a standalone file")
    template = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=os.path.dirname(__file__))).get_template(
        "events.html.j2"
    )
    template.stream(events=merge_events(event_files)).dump(os.path.join(output_folder, "events.html"))


@JunitTestCase()
def download_logs(
    client: InventoryClient,
    cluster: dict,
    dest: str,
    must_gather: bool,
    update_by_events: bool = False,
    retry_interval: int = RETRY_INTERVAL,
):
    if "hosts" not in cluster or len(cluster["hosts"]) == 0:
        try:
            cluster["hosts"] = client.get_cluster_hosts(cluster_id=cluster["id"], get_unregistered_clusters=True)
        except assisted_service_client.rest.ApiException:
            # if we're dealing with a deleted cluster, it might have been garbage-collected, so we're only logging it
            if cluster["deleted_at"] is None:
                raise

            log.debug(
                "Couldn't fetch hosts for cluster %s, which has been deleted at %s",
                cluster["id"],
                cluster["deleted_at"],
            )

    output_folder = get_logs_output_folder(dest, cluster)
    if not is_update_needed(output_folder, update_by_events, client, cluster):
        log.info(f"Skipping, no need to update {output_folder}.")
        return

    recreate_folder(output_folder)
    recreate_folder(os.path.join(output_folder, "cluster_files"))

    try:
        infra_envs = client.get_infra_envs_by_cluster_id(cluster["id"])
        write_metadata_file(client, cluster, infra_envs, os.path.join(output_folder, "metadata.json"))

        for cluster_file in (
            "bootstrap.ign",
            "master.ign",
            "worker.ign",
        ):
            with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
                file_path = os.path.join(output_folder, "cluster_files", cluster_file)
                client.download_and_save_file(cluster["id"], cluster_file, file_path)
                censor_sensitive_sources(file_path)

        with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
            install_config = Path(output_folder) / "cluster_files" / "install-config.yaml"
            client.download_and_save_file(cluster["id"], "install-config.yaml", str(install_config))

            install_config_content: dict = json.loads(install_config.read_text())

            if "pullSecret" in install_config_content:
                install_config_content["pullSecret"] = "censored"

            install_config.write_text(
                json.dumps(install_config_content, indent=2),
                encoding="utf-8",
            )

        with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
            download_manifests(client, cluster["id"], output_folder)

        for host in cluster["hosts"]:
            with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
                file_path = os.path.join(output_folder, "cluster_files", f"host_{host['id']}.ign")
                client.download_host_ignition(
                    host["infra_env_id"], host["id"], os.path.join(output_folder, "cluster_files")
                )
                censor_sensitive_sources(file_path)

        gather_event_files(client, cluster, infra_envs, output_folder)

        with SuppressAndLog(assisted_service_client.rest.ApiException, KeyboardInterrupt):
            are_masters_in_configuring_state = are_host_progress_in_stage(
                cluster["hosts"], [HostsProgressStages.CONFIGURING], 2
            )
            are_masters_in_join_or_done_state = are_host_progress_in_stage(
                cluster["hosts"], [HostsProgressStages.JOINED, HostsProgressStages.DONE], 2
            )
            max_retries = MUST_GATHER_MAX_RETRIES if are_masters_in_join_or_done_state else MAX_RETRIES
            is_controller_expected = cluster["status"] == ClusterStatus.INSTALLED or are_masters_in_configuring_state
            min_number_of_logs = min_number_of_log_files(cluster, is_controller_expected)

            for i in range(max_retries):
                cluster_logs_tar = os.path.join(output_folder, f"cluster_{cluster['id']}_logs.tar")

                with suppress(FileNotFoundError):
                    os.remove(cluster_logs_tar)

                client.download_cluster_logs(cluster["id"], cluster_logs_tar)
                try:
                    verify_logs_uploaded(
                        cluster_logs_tar,
                        min_number_of_logs,
                        installation_success=(cluster["status"] == ClusterStatus.INSTALLED),
                        check_oc=are_masters_in_join_or_done_state,
                    )
                    break
                except AssertionError as ex:
                    log.warning("Cluster logs verification failed: %s", ex)

                    # Skip sleeping on last retry
                    if i < MAX_RETRIES - 1:
                        log.info(f"Going to retry in {retry_interval} seconds")
                        time.sleep(retry_interval)

        if must_gather:
            with SuppressAndLog(assisted_service_client.rest.ApiException):
                kubeconfig_path = os.path.join(output_folder, "kubeconfig-noingress")
                client.download_kubeconfig_no_ingress(cluster["id"], kubeconfig_path)

                config_etc_hosts(
                    cluster["name"],
                    cluster["base_dns_domain"],
                    client.get_api_vip(cluster, cluster["id"]),
                )
                download_must_gather(kubeconfig_path, output_folder)

    finally:
        run_command(f"chmod -R ugo+rx '{output_folder}'")


@JunitTestCase()
def download_logs_kube_api(
    api_client: ApiClient, cluster_name: str, namespace: str, dest: str, must_gather: bool, management_kubeconfig: str
):
    cluster_deployment = ClusterDeployment(
        kube_api_client=api_client,
        name=cluster_name,
        namespace=namespace,
    )

    agent_cluster_install = AgentClusterInstall(
        kube_api_client=api_client,
        name=cluster_deployment.get()["spec"]["clusterInstallRef"]["name"],
        namespace=namespace,
    )

    output_folder = os.path.join(dest, f"{cluster_name}")
    recreate_folder(output_folder)

    try:
        with SuppressAndLog(requests.exceptions.RequestException, ConnectionError):
            collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install, output_folder)

        if must_gather:
            recreate_folder(os.path.join(output_folder, "must-gather"))
            with SuppressAndLog(Exception):
                # in case of hypershift
                if namespace.startswith("clusters"):
                    log.info("Dumping hypershift files")
                    hypershift = HyperShift(name=cluster_name, kube_api_client=api_client)
                    hypershift.dump(os.path.join(output_folder, "dump"), management_kubeconfig)
                    download_must_gather(hypershift.kubeconfig_path, output_folder)

                else:
                    _must_gather_kube_api(cluster_name, cluster_deployment, agent_cluster_install, output_folder)

    finally:
        run_command(f"chmod -R ugo+rx '{output_folder}'")


def _must_gather_kube_api(cluster_name, cluster_deployment, agent_cluster_install, output_folder):
    kubeconfig_path = os.path.join(output_folder, "kubeconfig", f"{cluster_name}_kubeconfig.yaml")
    agent_spec = agent_cluster_install.get_spec()
    agent_cluster_install.download_kubeconfig(kubeconfig_path=kubeconfig_path)
    log.info("Agent cluster install spec %s", agent_spec)

    # in case of single node we should set node ip and not vip
    if agent_spec.get("provisionRequirements", {}).get("controlPlaneAgents", 3) == 1:
        kube_api_ip = get_ip_for_single_node(
            cluster_deployment, is_cidr_is_ipv4(agent_spec["networking"]["machineNetwork"][0]["cidr"])
        )
    else:
        kube_api_ip = agent_cluster_install.get_spec()["apiVIP"]

    config_etc_hosts(
        cluster_name,
        cluster_deployment.get()["spec"]["baseDomain"],
        kube_api_ip,
    )
    download_must_gather(kubeconfig_path, output_folder)


def get_cluster_events_path(cluster, output_folder):
    return os.path.join(output_folder, f"cluster_{cluster['id']}_events.json")


def get_cluster_metadata(output_folder):
    with open(os.path.join(output_folder, "metadata.json"), "rt") as f:
        return json.load(f)


def get_infraenv_events_path(infra_env_id, output_folder):
    return os.path.join(output_folder, f"infraenv_{infra_env_id}_events.json")


@JunitTestCase()
def get_logs_output_folder(dest: str, cluster: dict) -> str:
    started_at = cluster["install_started_at"]

    if isinstance(started_at, str):
        started_at = isoparse(started_at)

    if isinstance(started_at, datetime):
        started_at = started_at.strftime(TIME_FORMAT)

    return os.path.join(dest, f"{started_at}_{cluster['id']}")


@JunitTestCase()
def write_metadata_file(client: InventoryClient, cluster: dict, infra_envs: list[dict], file_name: str):
    d = {"cluster": cluster}
    d.update(client.get_versions())

    d["infraenvs"] = infra_envs

    with suppress(KeyError):
        d["link"] = f"{get_ui_url_from_api_url(client.inventory_url)}/clusters/{cluster['id']}"

    with open(file_name, "w") as metadata_file:
        json.dump(d, metadata_file, sort_keys=True, indent=4, default=str)


def get_ui_url_from_api_url(api_url: str):
    known_urls = {
        "https://api.openshift.com/": "https://console.redhat.com/openshift/assisted-installer",
        "https://api.stage.openshift.com/": "https://console.dev.redhat.com/openshift",
    }

    for k, v in known_urls.items():
        if api_url in k:
            return v
    else:
        raise KeyError(api_url)


@JunitTestCase()
def download_must_gather(kubeconfig: str, dest_dir: str, describe_cluster_operators: bool = True):
    must_gather_dir = f"{dest_dir}/must-gather-dir"
    os.mkdir(must_gather_dir)

    log.info(f"Downloading must-gather to {must_gather_dir}, kubeconfig {kubeconfig}")
    command = (
        f"oc --insecure-skip-tls-verify --kubeconfig={kubeconfig} adm must-gather"
        f" --dest-dir {must_gather_dir} > {must_gather_dir}/must-gather.log"
    )
    try:
        run_command(command, shell=True, raise_errors=True)

    except RuntimeError as ex:
        log.warning(f"Failed to run must gather: {ex}")

    if describe_cluster_operators:
        run_oc_describe_cluster_operators(kubeconfig, dest_dir)

    log.debug("Archiving %s...", must_gather_dir)
    with tarfile.open(f"{dest_dir}/must-gather.tar.gz", "w:gz") as tar:
        tar.add(must_gather_dir, arcname=os.path.sep)

    log.debug("Removing must-gather directory %s after we archived it", must_gather_dir)
    shutil.rmtree(must_gather_dir)


@JunitTestCase()
def gather_sosreport_data(output_dir: str):
    sosreport_output = os.path.join(output_dir, "sosreport")
    recreate_folder(sosreport_output)

    nodes = []
    # Find matching controller by listing nodes
    for controller_class in [LibvirtController, VSphereController, NutanixController]:
        log.debug(f"Looking up nodes using controller {controller_class.__name__}")
        try:
            controller = controller_class(TerraformConfig(), ClusterConfig())
            nodes = controller.list_nodes()
            if len(nodes) != 0:
                log.debug(f"Using controller {controller_class.__name__} to fetch SOS report from {len(nodes)} nodes")
                break
        except Exception as e:
            log.debug(f"Error fetching nodes using controller {controller_class.__name__}: {e}")

    run_concurrently(
        jobs=[(gather_sosreport_from_node, node, sosreport_output) for node in nodes],
        timeout=60 * 20,
    )


def run_oc_describe_cluster_operators(kubeconfig: str, dest_dir: str):
    log.info(f"Describing cluster operators using kubeconfig: {kubeconfig}")
    command = (
        f"oc --insecure-skip-tls-verify --kubeconfig={kubeconfig} describe co" f" > {dest_dir}/cluster_operators.yaml"
    )
    with SuppressAndLog(RuntimeError):
        run_command(command, shell=True, raise_errors=True)


def gather_sosreport_from_node(node: Node, destination_dir: str):
    try:
        node.upload_file(SOSREPORT_SCRIPT, "/tmp/man_sosreport.sh")
        node.run_command("chmod a+x /tmp/man_sosreport.sh")
        log.debug(f"Running SOS report collection on node {node.ips}")
        try:
            node.run_command("sudo /tmp/man_sosreport.sh")
            log.debug("sosreport.sh completed")
        except Exception as e:
            log.debug(f"Exception in man_sosreport.sh: {e}")
            raise
        try:
            log.debug("Fetching SOS report")
            dest_file = os.path.join(destination_dir, f"sosreport-{node.name}.tar.xz")
            node.download_file("/var/tmp/sosreport.tar.xz", dest_file)
            log.debug(f"Fetched SOS report to {dest_file}")
        except Exception as e:
            log.debug(f"Exception fetching sosreport: {e}")
            raise

    except (TimeoutError, RuntimeError, SSHException, SCPException):
        log.exception("Failed accessing node %s for sosreport data gathering", node)


def collect_debug_info_from_cluster(cluster_deployment, agent_cluster_install, output_folder=None):
    cluster_name = cluster_deployment.ref.name
    if not output_folder:
        output_folder = f"build/{cluster_name}"
        recreate_folder(output_folder)
    aci = agent_cluster_install.get()
    debug_info = aci["status"]["debugInfo"]

    try:
        log.info("Collecting debugInfo events from cluster to %s, debug info %s", output_folder, debug_info)
        fetch_url_and_write_to_file("eventsURL", "events.json", debug_info, output_folder)
        log.info("Collecting debugInfo logs from cluster")
        fetch_url_and_write_to_file("logsURL", "logs.tar", debug_info, output_folder)
    except Exception as err:
        log.exception(f"Failed to collect debug info for cluster {cluster_name} ({err})")


def fetch_url_and_write_to_file(url_key, file_name, debug_info, output_folder):
    if url_key in debug_info:
        logs_url = debug_info[url_key]
        content = fetch_url(logs_url)
        output_file = os.path.join(output_folder, file_name)
        with open(output_file, "wb") as _file:
            _file.write(content)
    else:
        log.warning(f"{url_key} is not available")
