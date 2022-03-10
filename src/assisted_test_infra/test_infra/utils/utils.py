# -*- coding: utf-8 -*-
import datetime
import errno
import ipaddress
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
from contextlib import contextmanager
from distutils.dir_util import copy_tree
from distutils.util import strtobool
from functools import wraps
from pathlib import Path
from string import ascii_lowercase
from typing import List, Tuple, Union

import filelock
import requests
import waiting
from requests import Session
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException
from requests.models import HTTPError
from retry import retry

import consts
from assisted_test_infra.test_infra.utils import oc_utils
from service_client import log


def download_file(url: str, local_filename: str, verify_ssl: bool, tries=5) -> Path:
    @retry(exceptions=(RuntimeError, HTTPError), tries=tries, delay=10, logger=log)
    def _download_file() -> Path:
        with requests.get(url, stream=True, verify=verify_ssl) as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        return Path(local_filename)

    return _download_file()


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


def run_command(command, shell=False, raise_errors=True, env=None, cwd=None):
    command = command if shell else shlex.split(command)
    process = subprocess.run(
        command, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, universal_newlines=True, cwd=cwd
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


def run_command_with_output(command, env=None, cwd=None):
    with subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
        env=env,
        cwd=cwd,
    ) as p:
        for line in p.stdout:
            print(line, end="")  # process line here

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)


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


def are_host_progress_in_stage(hosts, stages, nodes_count=1):
    log.info("Checking hosts installation stage")
    hosts_in_stage = [host for host in hosts if (host["progress"]["current_stage"]) in stages]
    if len(hosts_in_stage) >= nodes_count:
        return True
    host_info = [(host["id"], (host["progress"]["current_stage"])) for host in hosts]
    log.info(
        f"Asked {nodes_count} hosts to be in one of the stages from {stages} and currently "
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
            waiting_for=f"Cluster to be in status {statuses}",
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
        log.warning("Directory %s doesn't exist. Please create it", folder)
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
        run_command(f"chmod -R ugo+rx '{folder}'")


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
        # Resolve the service ip and port
        url, _, _ = run_command(
            f"kubectl get svc {service} -n {namespace} "
            f"-o=jsonpath='http://{{.status.loadBalancer.ingress[0].ip}}:"
            f'{{.spec.ports[?(@.name=="{service}")].port}}\''
        )
        if is_assisted_service_reachable(url):
            return url

        raise RuntimeError(f"The parsed url {url} to service {service} in {namespace} namespace was not reachable.]")


def is_assisted_service_reachable(url):
    try:
        r = requests.get(url + "/health", timeout=10, verify=False)
        return r.status_code == 200
    except (requests.ConnectionError, requests.ConnectTimeout, requests.RequestException):
        return False


def get_tf_folder(cluster_name, namespace=None):
    warnings.warn(
        "get_tf_folder is deprecated. Use utils.TerraformControllerUtil.get_folder instead.", DeprecationWarning
    )
    folder_name = f"{cluster_name}__{namespace}" if namespace else f"{cluster_name}"
    return os.path.join(consts.TF_FOLDER, folder_name)


def on_exception(*, message=None, callback=None, silent=False, errors=(Exception,)):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except errors as e:
                if message:
                    log.exception(message)
                if callback:
                    callback(e)
                if silent:
                    return
                raise

        return wrapped

    return decorator


@contextmanager
def file_lock_context(filepath="/tmp/src.lock", timeout=300):
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


def create_ip_address_list(node_count, starting_ip_addr):
    return [str(ipaddress.ip_address(starting_ip_addr) + i) for i in range(node_count)]


def create_ip_address_nested_list(node_count, starting_ip_addr):
    return [[str(ipaddress.ip_address(starting_ip_addr) + i)] for i in range(node_count)]


def is_cidr_is_ipv4(cidr):
    return type(cidr) == ipaddress.IPv4Interface


def create_empty_nested_list(node_count):
    return [[] for _ in range(node_count)]


def get_libvirt_nodes_from_tf_state(network_names: Union[List[str], Tuple[str]], tf_state):
    nodes = extract_nodes_from_tf_state(tf_state, network_names, consts.NodeRoles.MASTER)
    nodes.update(extract_nodes_from_tf_state(tf_state, network_names, consts.NodeRoles.WORKER))
    return nodes


def extract_nodes_from_tf_state(tf_state, network_names, role):
    """
    :tags: QE
    """
    data = {}
    for domains in [
        r["instances"] for r in tf_state.resources if r["type"] == "libvirt_domain" and role in r["module"]
    ]:
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
            log.info("Updated /etc/hosts with record: %s %s", api_vip, api_vip_dnsname)


def run_container(container_name, image, flags=None, command=""):
    log.info(f"Running Container {container_name}")
    run_container_cmd = f"podman {consts.PODMAN_FLAGS} run --name {container_name}"

    flags = flags or []
    for flag in flags:
        run_container_cmd += f" {flag}"

    run_container_cmd += f" {image} {command}"

    run_command(run_container_cmd, shell=True)


def remove_running_container(container_name):
    log.info(f"Removing Container {container_name}")
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
    except FileExistsError as e:
        raise FileExistsError(
            f"{kubeconfig_dir} should be a directory. Remove the old kubeconfig file and retry."
        ) from e

    return kubeconfig_path


def get_default_openshift_version(client=None) -> str:
    if client:
        log.info("Using client to get default openshift version")
        ocp_versions_dict = client.get_openshift_versions()
        versions = [k for k, v in ocp_versions_dict.items() if v.get("default", False)]
    else:
        log.info(f"Reading {consts.RELEASE_IMAGES_PATH} to get default openshift version")
        with open(consts.RELEASE_IMAGES_PATH, "r") as f:
            release_images = json.load(f)
            versions = [v.get("openshift_version") for v in release_images if v.get("default", False)]

    assert len(versions) == 1, f"There should be exactly one default version {versions}"
    return versions[0]


def get_openshift_version(allow_default=True, client=None) -> str:
    """
    Return the openshift version that needs to be handled
    according to the following process:

    1. In case env var OPENSHIFT_VERSION is defined - return it.
    2. In case env var OPENSHIFT_INSTALL_RELEASE_IMAGE is defined to override the release image -
    extract its OCP version.
    3. In case allow_default is enabled, return the default supported version by assisted-service.
        3.1 If a client is provided, request the versions from the service (supports remote service).
        3.2 Otherwise, Get from the JSON file in assisted-service repository.
    """

    version = get_env("OPENSHIFT_VERSION")
    if version:
        return version

    release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")

    if release_image:
        with pull_secret_file() as pull_secret:
            stdout, _, _ = run_command(
                f"oc adm release info '{release_image}' --registry-config '{pull_secret}' -o json |"
                f" jq -r '.metadata.version' | grep -oP '\\d\\.\\d+'",
                shell=True,
            )
        return stdout

    if allow_default:
        return get_default_openshift_version(client)

    return None


def get_openshift_release_image(allow_default=True):
    release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")

    if not release_image:
        # TODO: Support remote client. kube-api client needs to respond supported versions
        ocp_version = get_openshift_version(allow_default=allow_default)

        with open(consts.RELEASE_IMAGES_PATH, "r") as f:
            release_images = json.load(f)

        release_image = [
            v.get("url")
            for v in release_images
            if v.get("openshift_version") == ocp_version and v.get("cpu_architecture") == "x86_64"
        ][0]

    return release_image


def copy_template_tree(dst: str):
    copy_tree(src=consts.TF_TEMPLATES_ROOT, dst=dst)


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
        raise Exception(f"Failed to GET: {url} ({err})") from err


def run_marked_fixture(old_value, marker_name, request):
    marker = request.node.get_closest_marker(marker_name)
    if marker and marker.args and marker.args[0]:
        fixture_name = marker.args[0]
        # execute fixture
        return request.getfixturevalue(fixture_name)
    return old_value


def get_kubeapi_protocol_options() -> List[Tuple[bool, bool]]:
    is_ipv4 = get_env("IPv4")
    is_ipv6 = get_env("IPv6")

    is_ipv4 = bool(strtobool(is_ipv4)) if is_ipv4 else None
    is_ipv6 = bool(strtobool(is_ipv6)) if is_ipv6 else None

    if is_ipv6 and is_ipv4:  # dual-stack
        return [(True, True)]

    if is_ipv4:  # IPv4 only
        return [(True, False)]

    if is_ipv6:  # IPv6 only
        return [(False, True)]

    return [(False, True), (True, False)]
