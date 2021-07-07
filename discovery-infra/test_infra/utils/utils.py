# -*- coding: utf-8 -*-
import datetime
import errno
import ipaddress
import itertools
import json
import logging
import os
import random
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
import warnings
import xml.dom.minidom as md
from contextlib import contextmanager
from distutils.dir_util import copy_tree
from functools import wraps
from pathlib import Path
from string import ascii_lowercase
from typing import List, Tuple, Union

import filelock
import libvirt
import oc_utils
import requests
import waiting
from logger import log
from requests import Session
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException
from requests.models import HTTPError
from retry import retry

import test_infra.consts as consts
from test_infra.consts import env_defaults
from test_infra.utils import logs_utils

conn = libvirt.open("qemu:///system")


def scan_for_free_port(starting_port: int, step: int = 200):
    for port in range(starting_port, starting_port + step):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("0.0.0.0", port))
                sock.listen()
            except OSError as e:
                if e.errno != errno.EADDRINUSE:
                    raise
                continue

            return port

    raise RuntimeError("could not allocate free port for proxy")


def run_command(command, shell=False, raise_errors=True, env=None):
    command = command if shell else shlex.split(command)
    process = subprocess.run(
        command, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, universal_newlines=True
    )

    def _io_buffer_to_str(buf):
        if hasattr(buf, "read"):
            buf = buf.read().decode()
        return buf

    out = _io_buffer_to_str(process.stdout).strip()
    err = _io_buffer_to_str(process.stderr).strip()

    if raise_errors and process.returncode != 0:
        raise RuntimeError(f"command: {command} exited with an error: {err} " f"code: {process.returncode}")

    return out, err, process.returncode


def run_command_with_output(command, env=None):
    with subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
        env=env,
    ) as p:
        for line in p.stdout:
            print(line, end="")  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


def wait_till_nodes_are_ready(nodes_count, network_name):
    log.info("Wait till %s nodes will be ready and have ips", nodes_count)
    try:
        waiting.wait(
            lambda: len(get_network_leases(network_name)) >= nodes_count,
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT * nodes_count,
            sleep_seconds=10,
            waiting_for="Nodes to have ips",
        )
        log.info("All nodes have booted and got ips")
    except BaseException:
        log.error(
            "Not all nodes are ready. Current dhcp leases are %s",
            get_network_leases(network_name),
        )
        raise


# Require wait_till_nodes_are_ready has finished and all nodes are up
def get_libvirt_nodes_mac_role_ip_and_name(network_name):
    nodes_data = {}
    try:
        leases = get_network_leases(network_name)
        for lease in leases:
            nodes_data[lease["mac"]] = {
                "ip": lease["ipaddr"],
                "name": lease["hostname"],
                "role": consts.NodeRoles.WORKER
                if consts.NodeRoles.WORKER in lease["hostname"]
                else consts.NodeRoles.MASTER,
            }
        return nodes_data
    except BaseException:
        log.error(
            "Failed to get nodes macs from libvirt. Output is %s",
            get_network_leases(network_name),
        )
        raise


def get_libvirt_nodes_macs(network_name):
    return [lease["mac"] for lease in get_network_leases(network_name)]


def are_all_libvirt_nodes_in_cluster_hosts(client, cluster_id, network_name):
    hosts_macs = client.get_hosts_id_with_macs(cluster_id)
    return all(
        mac.lower() in map(str.lower, itertools.chain(*hosts_macs.values()))
        for mac in get_libvirt_nodes_macs(network_name)
    )


def are_libvirt_nodes_in_cluster_hosts(client, cluster_id, num_nodes):
    hosts_macs = client.get_hosts_id_with_macs(cluster_id)
    num_macs = len([mac for mac in hosts_macs if mac != ""])
    return num_macs >= num_nodes


def get_cluster_hosts_with_mac(client, cluster_id, macs):
    return [client.get_host_by_mac(cluster_id, mac) for mac in macs]


def to_utc(timestr):
    return time.mktime(datetime.datetime.strptime(timestr, "%Y-%m-%dT%H:%M:%S.%fZ").timetuple())


def get_tfvars(tf_folder):
    tf_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tf_json_file) as _file:
        tfvars = json.load(_file)
    return tfvars


def set_tfvars(tf_folder, tfvars_json):
    tf_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tf_json_file, "w") as _file:
        json.dump(tfvars_json, _file)


def are_hosts_in_status(hosts, nodes_count, statuses, fall_on_error_status=True):
    hosts_in_status = [host for host in hosts if host["status"] in statuses]
    if len(hosts_in_status) >= nodes_count:
        return True
    elif fall_on_error_status and len([host for host in hosts if host["status"] == consts.NodesStatus.ERROR]) > 0:
        hosts_in_error = [
            (i, host["id"], host["requested_hostname"], host["role"], host["status"], host["status_info"])
            for i, host in enumerate(hosts, start=1)
            if host["status"] == consts.NodesStatus.ERROR
        ]
        log.error("Some of the hosts are in insufficient or error status. Hosts in error %s", hosts_in_error)
        raise Exception("All the nodes must be in valid status, but got some in error")

    log.info(
        "Asked hosts to be in one of the statuses from %s and currently hosts statuses are %s",
        statuses,
        [
            (i, host["id"], host["requested_hostname"], host["role"], host["status"], host["status_info"])
            for i, host in enumerate(hosts, start=1)
        ],
    )
    return False


def wait_till_hosts_with_macs_are_in_status(
    client,
    cluster_id,
    macs,
    statuses,
    timeout=consts.NODES_REGISTERED_TIMEOUT,
    fall_on_error_status=True,
    interval=5,
):
    log.info("Wait till %s nodes are in one of the statuses %s", len(macs), statuses)

    waiting.wait(
        lambda: are_hosts_in_status(
            get_cluster_hosts_with_mac(client, cluster_id, macs),
            len(macs),
            statuses,
            fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Nodes to be in of the statuses %s" % statuses,
    )


def wait_till_all_hosts_are_in_status(
    client,
    cluster_id,
    nodes_count,
    statuses,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
    fall_on_error_status=True,
    interval=5,
):
    log.info("Wait till %s nodes are in one of the statuses %s", nodes_count, statuses)

    waiting.wait(
        lambda: are_hosts_in_status(
            client.get_cluster_hosts(cluster_id),
            nodes_count,
            statuses,
            fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Nodes to be in of the statuses %s" % statuses,
    )


def wait_till_at_least_one_host_is_in_status(
    client,
    cluster_id,
    statuses,
    nodes_count=1,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
    fall_on_error_status=True,
    interval=5,
):
    log.info("Wait till 1 node is in one of the statuses %s", statuses)

    waiting.wait(
        lambda: are_hosts_in_status(
            client.get_cluster_hosts(cluster_id),
            nodes_count,
            statuses,
            fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Node to be in of the statuses %s" % statuses,
    )


def wait_till_specific_host_is_in_status(
    client,
    cluster_id,
    host_name,
    nodes_count,
    statuses,
    timeout=consts.NODES_REGISTERED_TIMEOUT,
    fall_on_error_status=True,
    interval=5,
):
    log.info(f"Wait till {nodes_count} host is in one of the statuses: {statuses}")

    waiting.wait(
        lambda: are_hosts_in_status(
            [client.get_host_by_name(cluster_id, host_name)],
            nodes_count,
            statuses,
            fall_on_error_status,
        ),
        timeout_seconds=timeout,
        sleep_seconds=interval,
        waiting_for="Node to be in of the statuses %s" % statuses,
    )


def wait_till_at_least_one_host_is_in_stage(
    client,
    cluster_id,
    stages,
    nodes_count=1,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT / 2,
    interval=5,
):
    log.info(f"Wait till {nodes_count} node is in stage {stages}")
    try:
        waiting.wait(
            lambda: are_host_progress_in_stage(
                client.get_cluster_hosts(cluster_id),
                stages,
                nodes_count,
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Node to be in of the stage %s" % stages,
        )
    except BaseException:
        hosts = client.get_cluster_hosts(cluster_id)
        log.error(
            f"All nodes stages: "
            f"{[host['progress']['current_stage'] for host in hosts]} "
            f"when waited for {stages}"
        )
        raise


def are_host_progress_in_stage(hosts, stages, nodes_count=1):
    log.info("Checking hosts installation stage")
    hosts_in_stage = [host for host in hosts if (host["progress"]["current_stage"]) in stages]
    if len(hosts_in_stage) >= nodes_count:
        return True
    host_info = [(host["id"], (host["progress"]["current_stage"])) for host in hosts]
    log.info(
        f"Asked {nodes_count} hosts to be in one of the statuses from {stages} and currently "
        f"hosts statuses are {host_info}"
    )
    return False


def wait_till_cluster_is_in_status(
    client,
    cluster_id,
    statuses: List[str],
    timeout=consts.NODES_REGISTERED_TIMEOUT,
    interval=30,
    break_statuses: List[str] = None,
):
    log.info("Wait till cluster %s is in status %s", cluster_id, statuses)
    try:
        if break_statuses:
            statuses += break_statuses
        waiting.wait(
            lambda: is_cluster_in_status(client=client, cluster_id=cluster_id, statuses=statuses),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Cluster to be in status %s" % statuses,
        )
        if break_statuses and is_cluster_in_status(client, cluster_id, break_statuses):
            raise BaseException(
                f"Stop installation process, " f"cluster is in status {client.cluster_get(cluster_id).status}"
            )
    except BaseException:
        log.error("Cluster status is: %s", client.cluster_get(cluster_id).status)
        raise


def is_cluster_in_status(client, cluster_id, statuses):
    log.info("Is cluster %s in status %s", cluster_id, statuses)
    try:
        cluster_status = client.cluster_get(cluster_id).status
        if cluster_status in statuses:
            return True
        else:
            log.info(f"Cluster not yet in its required status. " f"Current status: {cluster_status}")
            return False
    except BaseException:
        log.exception("Failed to get cluster %s info", cluster_id)


def get_cluster_validation_value(cluster_info, validation_section, validation_id):
    found_status = "validation not found"
    validations = json.loads(cluster_info.validations_info)
    for validation in validations[validation_section]:
        if validation["id"] == validation_id:
            found_status = validation["status"]
            break
    return found_status


def get_host_validation_value(cluster_info, host_id, validation_section, validation_id):
    for host in cluster_info.hosts:
        if host.id != host_id:
            continue
        found_status = "validation not found"
        validations = json.loads(host.validations_info)
        for validation in validations[validation_section]:
            if validation["id"] == validation_id:
                found_status = validation["status"]
                break
        return found_status
    return "host not found"


def get_random_name(length=8):
    return "".join(random.choice(ascii_lowercase) for _ in range(length))


def folder_exists(file_path):
    folder = Path(file_path).parent
    if not folder:
        log.warn("Directory %s doesn't exist. Please create it", folder)
        return False
    return True


def recreate_folder(folder, with_chmod=True, force_recreate=True):
    is_exists = os.path.isdir(folder)
    if is_exists and force_recreate:
        shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)
    elif not is_exists:
        os.makedirs(folder, exist_ok=True)

    if with_chmod:
        run_command("chmod -R ugo+rx '%s'" % folder)


def get_assisted_service_url_by_args(args, wait=True):
    if hasattr(args, "inventory_url") and args.inventory_url:
        return args.inventory_url

    kwargs = {"service": args.service_name, "namespace": args.namespace}
    if args.oc_mode:
        get_url = get_remote_assisted_service_url
        kwargs["oc"] = oc_utils.get_oc_api_client(token=args.oc_token, server=args.oc_server)
        kwargs["scheme"] = args.oc_scheme
    else:
        get_url = get_local_assisted_service_url
        kwargs["deploy_target"] = args.deploy_target

    return retry(
        tries=5 if wait else 1,
        delay=3,
        backoff=2,
        exceptions=(requests.ConnectionError, requests.ConnectTimeout, requests.RequestException),
    )(get_url)(**kwargs)


def get_remote_assisted_service_url(oc, namespace, service, scheme):
    log.info("Getting oc %s URL in %s namespace", service, namespace)
    service_urls = oc_utils.get_namespaced_service_urls_list(
        client=oc, namespace=namespace, service=service, scheme=scheme
    )
    for url in service_urls:
        if is_assisted_service_reachable(url):
            return url

    raise RuntimeError(f"could not find any reachable url to {service} service " f"in {namespace} namespace")


def get_local_assisted_service_url(namespace, service, deploy_target):
    if deploy_target in ["onprem"]:
        assisted_hostname_or_ip = os.environ["ASSISTED_SERVICE_HOST"]
        return f"http://{assisted_hostname_or_ip}:8090"
    elif deploy_target == "ocp":
        res = subprocess.check_output("ip route get 1", shell=True).split()[6]
        ip = str(res, "utf-8")
        return f"http://{ip}:7000"
    else:
        # default deploy target is minikube
        log.info("Getting minikube %s URL in %s namespace", service, namespace)
        ip, _, _ = run_command("kubectl get nodes -o=jsonpath={.items[0].status.addresses[0].address}")
        # resolve the service node port form the service internal port (Support multiple ports per service).
        port, _, _ = run_command(f"kubectl get svc assisted-service -n {namespace} "
                                 f"-o=jsonpath='{{.spec.ports[?(@.port==8090)].nodePort}}'")
        url = f"http://{ip}:{port}"
        if is_assisted_service_reachable(url):
            return url

        raise RuntimeError(f"could not find any reachable url to {service} service " f"in {namespace} namespace")


def is_assisted_service_reachable(url):
    try:
        r = requests.get(url + "/health", timeout=10, verify=False)
        return r.status_code == 200
    except (requests.ConnectionError, requests.ConnectTimeout, requests.RequestException):
        return False


def get_tf_folder(cluster_name, namespace=None):
    folder_name = f"{cluster_name}__{namespace}" if namespace else f"{cluster_name}"
    return os.path.join(consts.TF_FOLDER, folder_name)


def get_all_namespaced_clusters():
    if not os.path.isdir(consts.TF_FOLDER):
        return

    for dirname in os.listdir(consts.TF_FOLDER):
        res = get_name_and_namespace_from_dirname(dirname)
        if not res:
            continue
        name, namespace = res
        yield name, namespace


def get_name_and_namespace_from_dirname(dirname):
    if "__" in dirname:
        return dirname.rsplit("__", 1)

    log.warning(
        "Unable to extract cluster name and namespace from directory name %s. "
        "Directory name convention must be <cluster_name>:<namespace>",
        dirname,
    )


def on_exception(*, message=None, callback=None, silent=False, errors=(Exception,)):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except errors as e:
                if message:
                    logging.exception(message)
                if callback:
                    callback(e)
                if silent:
                    return
                raise

        return wrapped

    return decorator


@contextmanager
def file_lock_context(filepath="/tmp/discovery-infra.lock", timeout=300):
    logging.getLogger("filelock").setLevel(logging.ERROR)

    lock = filelock.FileLock(filepath, timeout)
    try:
        lock.acquire()
    except filelock.Timeout:
        log.info("Deleting lock file: %s " "since it exceeded timeout of: %d seconds", filepath, timeout)
        os.unlink(filepath)
        lock.acquire()

    try:
        yield
    finally:
        lock.release()


def _get_hosts_from_network(net):
    desc = md.parseString(net.XMLDesc())
    try:
        hosts = (
            desc.getElementsByTagName("network")[0]
            .getElementsByTagName("ip")[0]
            .getElementsByTagName("dhcp")[0]
            .getElementsByTagName("host")
        )
        return list(
            map(
                lambda host: {
                    "mac": host.getAttribute("mac"),
                    "ipaddr": host.getAttribute("ip"),
                    "hostname": host.getAttribute("name"),
                },
                hosts,
            )
        )
    except IndexError:
        return []


def _merge(leases, hosts):
    lips = [ls["ipaddr"] for ls in leases]
    ret = leases + [h for h in hosts if h["ipaddr"] not in lips]
    return ret


def get_network_leases(network_name):
    with file_lock_context():
        net = conn.networkLookupByName(network_name)
        leases = net.DHCPLeases()  # TODO: getting the information from the XML dump until dhcp-leases bug is fixed
        hosts = _get_hosts_from_network(net)
        return _merge(leases, hosts)


def create_ip_address_list(node_count, starting_ip_addr):
    return [str(ipaddress.ip_address(starting_ip_addr) + i) for i in range(node_count)]


def create_ip_address_nested_list(node_count, starting_ip_addr):
    return [[str(ipaddress.ip_address(starting_ip_addr) + i)] for i in range(node_count)]


def create_empty_nested_list(node_count):
    return [[] for _ in range(node_count)]


def get_libvirt_nodes_from_tf_state(network_names: Union[List[str], Tuple[str]], tf_state):
    nodes = extract_nodes_from_tf_state(tf_state, network_names, consts.NodeRoles.MASTER)
    nodes.update(extract_nodes_from_tf_state(tf_state, network_names, consts.NodeRoles.WORKER))
    return nodes


def extract_nodes_from_tf_state(tf_state, network_names, role):
    data = {}
    for domains in [r["instances"] for r in tf_state.resources if r["type"] == "libvirt_domain" and role in r["name"]]:
        for d in domains:
            for nic in d["attributes"]["network_interface"]:

                if nic["network_name"] not in network_names:
                    continue

                data[nic["mac"]] = {"ip": nic["addresses"], "name": d["attributes"]["name"], "role": role}

    return data


def get_env(env, default=None):
    res = os.environ.get(env, "").strip()
    if not res or res == '""':
        res = default
    return res


def touch(path):
    with open(path, "a"):
        os.utime(path, None)


def config_etc_hosts(cluster_name: str, base_dns_domain: str, api_vip: str):
    lock_file = "/tmp/test_etc_hosts.lock"
    api_vip_dnsname = "api." + cluster_name + "." + base_dns_domain
    with file_lock_context(lock_file):
        with open("/etc/hosts", "r") as f:
            hosts_lines = f.readlines()
        for i, line in enumerate(hosts_lines):
            if api_vip_dnsname in line:
                hosts_lines[i] = f"{api_vip} {api_vip_dnsname}\n"
                break
        else:
            hosts_lines.append(f"{api_vip} {api_vip_dnsname}\n")
        with open("/etc/hosts", "w") as f:
            f.writelines(hosts_lines)
            logging.info("Updated /etc/hosts with record: %s %s", api_vip, api_vip_dnsname)


def run_container(container_name, image, flags=None, command=""):
    logging.info(f"Running Container {container_name}")
    run_container_cmd = f"podman {consts.PODMAN_FLAGS} run --name {container_name}"

    flags = flags or []
    for flag in flags:
        run_container_cmd += f" {flag}"

    run_container_cmd += f" {image} {command}"

    run_command(run_container_cmd, shell=True)


def remove_running_container(container_name):
    logging.info(f"Removing Container {container_name}")
    container_rm_cmd = (
        f"podman {consts.PODMAN_FLAGS} stop {container_name} && podman" f" {consts.PODMAN_FLAGS} rm {container_name}"
    )
    run_command(container_rm_cmd, shell=True)


def get_kubeconfig_path(cluster_name: str) -> str:
    kubeconfig_dir = Path.cwd().joinpath(consts.DEFAULT_CLUSTER_KUBECONFIG_DIR_PATH)
    default = kubeconfig_dir.joinpath(f"kubeconfig_{cluster_name}")
    kubeconfig_path = get_env("KUBECONFIG", str(default))

    try:
        if kubeconfig_path == str(default):
            kubeconfig_dir.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        raise FileExistsError(f"{kubeconfig_dir} should be a directory. Remove the old kubeconfig file and retry.")

    return kubeconfig_path


def get_openshift_version(default=consts.DEFAULT_OPENSHIFT_VERSION):
    release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")

    if release_image:
        with pull_secret_file() as pull_secret:
            stdout, _, _ = run_command(
                f"oc adm release info '{release_image}' --registry-config '{pull_secret}' -o json |"
                f" jq -r '.metadata.version' | grep -oP '\\d\\.\\d+'",
                shell=True,
            )
        return stdout

    return get_env("OPENSHIFT_VERSION", default)


def get_openshift_release_image(ocp_version=consts.DEFAULT_OPENSHIFT_VERSION):
    release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")

    if not release_image:
        stdout, _, _ = run_command(
            f"jq -r '.[\"{ocp_version}\"].release_image' assisted-service/data/default_ocp_versions.json", shell=True
        )
        return stdout

    return release_image


def copy_template_tree(dst, none_platform_mode=False):
    copy_tree(
        src=consts.TF_TEMPLATE_NONE_PLATFORM_FLOW if none_platform_mode else consts.TF_TEMPLATE_BARE_METAL_FLOW, dst=dst
    )


@contextmanager
def pull_secret_file():
    pull_secret = os.environ.get("PULL_SECRET")

    try:
        json.loads(pull_secret)
    except json.JSONDecodeError as e:
        raise ValueError("Value of PULL_SECRET environment variable is not a valid JSON payload") from e

    with tempfile.NamedTemporaryFile(mode="w") as f:
        f.write(pull_secret)
        f.flush()
        yield f.name


def extract_installer(release_image, dest):
    logging.info("Extracting installer from %s to %s", release_image, dest)
    with pull_secret_file() as pull_secret:
        run_command(
            f"oc adm release extract --registry-config '{pull_secret}'"
            f" --command=openshift-install --to={dest} {release_image}"
        )


def update_hosts(client, cluster_id, libvirt_nodes, update_hostnames=False, update_roles=True):
    """
    Update names and/or roles of the hosts in a cluster from a dictionary of libvirt nodes.

    An entry from the dictionary is matched to a host by the host's MAC address (of any NIC).
    Entries that do not match any host in the cluster are ignored.

    Arguments:
        client -- An assisted service client
        cluster_id -- ID of the cluster to update
        libvirt_nodes -- A dictionary that may contain data about cluster hosts
        update_hostnames -- Whether hostnames must be set (default False)
        update_roles -- Whether host roles must be set (default True)
    """

    if not update_hostnames and not update_roles:
        logging.info("Skipping update roles and hostnames")
        return

    roles = []
    hostnames = []
    inventory_hosts = client.get_cluster_hosts(cluster_id)

    for libvirt_mac, libvirt_metadata in libvirt_nodes.items():
        for host in inventory_hosts:
            inventory = json.loads(host["inventory"])

            if libvirt_mac.lower() in map(
                lambda interface: interface["mac_address"].lower(),
                inventory["interfaces"],
            ):
                roles.append({"id": host["id"], "role": libvirt_metadata["role"]})
                hostnames.append({"id": host["id"], "hostname": libvirt_metadata["name"]})

    if not update_hostnames:
        hostnames = None

    if not update_roles:
        roles = None

    client.update_hosts(cluster_id=cluster_id, hosts_with_roles=roles, hosts_names=hostnames)


def get_assisted_controller_status(kubeconfig):
    log.info("Getting controller status")
    command = (
        f"oc --insecure-skip-tls-verify --kubeconfig={kubeconfig} --no-headers=true -n assisted-installer "
        f"get pods -l job-name=assisted-installer-controller"
    )
    response = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    if response.returncode != 0:
        log.error(f"failed to get controller status: {response.stderr}")
        return b""

    log.info(f"{response.stdout}")
    return response.stdout


def download_iso(image_url, image_path):
    with requests.get(image_url, stream=True, verify=False) as image, open(image_path, "wb") as out:
        for chunk in image.iter_content(chunk_size=1024):
            out.write(chunk)


def fetch_url(url, timeout=60, max_retries=5):
    """
    Returns the response content for the specified URL.
    Raises an exception in case of any failure.
    """
    try:
        retries = Retry(read=max_retries, status=max_retries, backoff_factor=0.5, status_forcelist=[500])
        s = Session()
        s.mount("http://", HTTPAdapter(max_retries=retries))

        log.info(f"Fetching URL: {url}")
        response = s.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except (RequestException, HTTPError) as err:
        raise Exception(f"Failed to GET: {url} ({err})")


# Deprecated functions


def get_logs_collected_at(client, cluster_id):
    warnings.warn(
        "get_logs_collected_at is deprecated and will be deleted soon." "Use test_infra.utils.logs_utils instead",
        DeprecationWarning,
    )
    logs_utils.get_logs_collected_at(client, cluster_id)


def wait_for_logs_complete(client, cluster_id, timeout, interval=60, check_host_logs_only=False):
    warnings.warn(
        "wait_for_logs_complete is deprecated and will be deleted soon."
        "Use test_infra.utils.wait_for_logs_complete instead",
        DeprecationWarning,
    )
    return logs_utils.wait_for_logs_complete(client, cluster_id, timeout, interval, check_host_logs_only)
