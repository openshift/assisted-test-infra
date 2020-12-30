# -*- coding: utf-8 -*-
import logging
import itertools
import ipaddress
import json
import os
import shlex
import shutil
import subprocess
import time
import tempfile
import datetime
import random
from string import ascii_lowercase
from pathlib import Path
from functools import wraps
from contextlib import contextmanager
import xml.dom.minidom as md

import libvirt
import waiting
import requests
import filelock
from test_infra import consts
import oc_utils
from logger import log
from retry import retry
from pprint import pformat
from distutils.dir_util import copy_tree

conn = libvirt.open("qemu:///system")


def run_command(command, shell=False, raise_errors=True):
    command = command if shell else shlex.split(command)
    process = subprocess.run(
        command,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    def _io_buffer_to_str(buf):
        if hasattr(buf, 'read'):
            buf = buf.read().decode()
        return buf

    out = _io_buffer_to_str(process.stdout).strip()
    err = _io_buffer_to_str(process.stderr).strip()

    if raise_errors and process.returncode != 0:
        raise RuntimeError(
            f'command: {command} exited with an error: {err} '
            f'code: {process.returncode}'
        )

    return out, err, process.returncode


def run_command_with_output(command):
    with subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True
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
    except:
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
    except:
        log.error(
            "Failed to get nodes macs from libvirt. Output is %s",
            get_network_leases(network_name),
        )
        raise

def wait_for_cvo_available():
    waiting.wait(
        lambda: is_cvo_available(),
        timeout_seconds=3600,
        sleep_seconds=20,
        waiting_for="CVO to become available",
    )


def is_cvo_available():
    try:
        res = subprocess.check_output("kubectl --kubeconfig=build/kubeconfig get clusterversion -o json", shell=True)
        conditions = json.loads(res)['items'][0]['status']['conditions']
        for condition in conditions:
            log.info(f"CVO condition <{condition['type']}> status is <{condition['status']}>, because: {condition['message']}")

            if condition['type'] == 'Available' and condition['status'] == 'True':
                return True
    except:
        log.info("exception in access the cluster api server")
    return False


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
    num_macs = len([mac for mac in hosts_macs if mac != ''])
    return num_macs >= num_nodes


def get_cluster_hosts_macs(client, cluster_id):
    return client.get_hosts_id_with_macs(cluster_id)


def get_cluster_hosts_with_mac(client, cluster_id, macs):
    return [client.get_host_by_mac(cluster_id, mac) for mac in macs]

def to_utc(timestr):
    return time.mktime(datetime.datetime.strptime(timestr, "%Y-%m-%dT%H:%M:%S.%fZ").timetuple())


def get_logs_collected_at(client, cluster_id):
    hosts = client.get_cluster_hosts(cluster_id)
    return [to_utc(host["logs_collected_at"]) for host in hosts]


def get_tfvars(tf_folder):
    tf_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tf_json_file) as _file:
        tfvars = json.load(_file)
    return tfvars


def set_tfvars(tf_folder, tfvars_json):
    tf_json_file = os.path.join(tf_folder, consts.TFVARS_JSON_NAME)
    with open(tf_json_file, "w") as _file:
        json.dump(tfvars_json, _file)


def get_tf_main(tf_folder):
    tf_file = os.path.join(tf_folder, consts.TF_MAIN_JSON_NAME)
    with open(tf_file) as _file:
        main_str = _file.read()
    return main_str


def set_tf_main(tf_folder, main_str):
    tf_file = os.path.join(tf_folder, consts.TF_MAIN_JSON_NAME)
    with open(tf_file, "w") as _file:
        main_str = _file.write(main_str)


def are_hosts_in_status(
        hosts, nodes_count, statuses, fall_on_error_status=True
):
    hosts_in_status = [host for host in hosts if host["status"] in statuses]
    if len(hosts_in_status) >= nodes_count:
        return True
    elif (
        fall_on_error_status
        and len([host for host in hosts if host["status"] == consts.NodesStatus.ERROR])
        > 0
    ):
        hosts_in_error = [
            host for host in hosts if host["status"] == consts.NodesStatus.ERROR
        ]
        log.error(
            "Some of the hosts are in insufficient or error status. Hosts in error %s",
            pformat(hosts_in_error),
        )
        raise Exception("All the nodes must be in valid status, but got some in error")

    log.info(
        "Asked hosts to be in one of the statuses from %s and currently hosts statuses are %s",
        statuses,
        [(host["id"], host["status"], host["status_info"]) for host in hosts],
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

    try:
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
    except:
        hosts = get_cluster_hosts_with_mac(client, cluster_id, macs)
        log.info("All nodes: %s", hosts)
        raise


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

    try:
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
    except:
        hosts = client.get_cluster_hosts(cluster_id)
        log.info("All nodes: %s", hosts)
        raise


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

    try:
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
    except:
        hosts = client.get_cluster_hosts(cluster_id)
        log.info("All nodes: %s", hosts)
        raise


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

    try:
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
    except:
        hosts = client.get_cluster_hosts(cluster_id)
        log.info("All nodes: %s", hosts)
        raise


def wait_till_at_least_one_host_is_in_stage(
    client,
    cluster_id,
    stages,
    nodes_count=1,
    timeout=consts.CLUSTER_INSTALLATION_TIMEOUT/2,
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
    except:
        hosts = client.get_cluster_hosts(cluster_id)
        log.error(f"All nodes stages: "
                  f"{[host['progress']['current_stage'] for host in hosts]} "
                  f"when waited for {stages}")
        raise


def are_host_progress_in_stage(hosts, stages, nodes_count=1):
    log.info("Checking hosts installation stage")
    hosts_in_stage = [host for host in hosts if
                      (host["progress"]["current_stage"]) in stages]
    if len(hosts_in_stage) >= nodes_count:
        return True
    host_info = [(host["id"], (host["progress"]["current_stage"])) for host in hosts]
    log.info(
        f"Asked {nodes_count} hosts to be in one of the statuses from {stages} and currently "
        f"hosts statuses are {host_info}")
    return False


def wait_till_cluster_is_in_status(
    client, cluster_id, statuses, timeout=consts.NODES_REGISTERED_TIMEOUT, interval=30
):
    log.info("Wait till cluster %s is in status %s", cluster_id, statuses)
    try:
        waiting.wait(
            lambda: is_cluster_in_status(
                client=client, 
                cluster_id=cluster_id, 
                statuses=statuses
            ),
            timeout_seconds=timeout,
            sleep_seconds=interval,
            waiting_for="Cluster to be in status %s" % statuses,
        )
    except:
        log.error("Cluster status is: %s", client.cluster_get(cluster_id).status)
        raise

def is_cluster_in_status(client, cluster_id, statuses):
    log.info("Is cluster %s in status %s", cluster_id, statuses)
    try:
        cluster_status = client.cluster_get(cluster_id).status
        if cluster_status in statuses:
            return True
        else:
            log.info(f"Cluster not yet in its required status. "
                     f"Current status: {cluster_status}")
            return False
    except:
        log.exception("Failed to get cluster %s info", cluster_id)


def get_cluster_validation_value(cluster_info, validation_section, validation_id):
    found_status = "validation not found"
    validations = json.loads(cluster_info.validations_info)
    for validation in validations[validation_section]:
        if validation['id'] == validation_id:
            found_status = validation['status']
            break
    return found_status


def get_host_validation_value(cluster_info, host_id, validation_section, validation_id):
    for host in cluster_info.hosts:
        if host.id != host_id:
            continue
        found_status = "validation not found"
        validations = json.loads(host.validations_info)
        for validation in validations[validation_section]:
            if validation['id'] == validation_id:
                found_status = validation['status']
                break
        return found_status
    return "host not found"


def get_random_name(length=8):
    return ''.join(random.choice(ascii_lowercase) for i in range(length))


def folder_exists(file_path):
    folder = Path(file_path).parent
    if not folder:
        log.warn("Directory %s doesn't exist. Please create it", folder)
        return False
    return True


def file_exists(file_path):
    return Path(file_path).exists()


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
    if hasattr(args, 'inventory_url') and args.inventory_url:
        return args.inventory_url

    kwargs = {
        'service': args.service_name,
        'namespace': args.namespace
    }
    if args.oc_mode:
        get_url = get_remote_assisted_service_url
        kwargs['oc'] = oc_utils.get_oc_api_client(
            token=args.oc_token,
            server=args.oc_server
        )
        kwargs['scheme'] = args.oc_scheme
    else:
        get_url = get_local_assisted_service_url
        kwargs['profile'] = args.profile
        kwargs['deploy_target'] = args.deploy_target

    return retry(
        tries=5 if wait else 1,
        delay=3,
        backoff=2,
        exceptions=(
            requests.ConnectionError,
            requests.ConnectTimeout,
            requests.RequestException
        )
    )(get_url)(**kwargs)


def get_remote_assisted_service_url(oc, namespace, service, scheme):
    log.info('Getting oc %s URL in %s namespace', service, namespace)
    service_urls = oc_utils.get_namespaced_service_urls_list(
        client=oc,
        namespace=namespace,
        service=service,
        scheme=scheme
    )
    for url in service_urls:
        if is_assisted_service_reachable(url):
            return url

    raise RuntimeError(
        f'could not find any reachable url to {service} service '
        f'in {namespace} namespace'
    )


def get_local_assisted_service_url(profile, namespace, service, deploy_target):
    if deploy_target == "podman-localhost":
        assisted_hostname_or_ip = os.environ["ASSISTED_SERVICE_HOST"]
        return f'http://{assisted_hostname_or_ip}:8090'
    elif deploy_target == "ocp":
        res = subprocess.check_output("ip route get 1", shell=True).split()[6]
        ip = str(res, "utf-8")
        return f'http://{ip}:7000'
    else:
        # default deploy target is minikube
        log.info('Getting minikube %s URL in %s namespace', service, namespace)
        url, _, _ = run_command(
            f'minikube  -p {profile} -n {namespace} service {service} --url'
        )
        if is_assisted_service_reachable(url):
            return url

        raise RuntimeError(
            f'could not find any reachable url to {service} service '
            f'in {namespace} namespace'
        )


def is_assisted_service_reachable(url):
    try:
        r = requests.get(url + '/health', timeout=10, verify=False)
        return r.status_code == 200
    except (
            requests.ConnectionError,
            requests.ConnectTimeout,
            requests.RequestException
    ):
        return False


def get_tf_folder(cluster_name, namespace=None):
    folder_name = f'{cluster_name}__{namespace}' if namespace else f'{cluster_name}'
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
    if '__' in dirname:
        return dirname.rsplit('__', 1)

    log.warning(
        'Unable to extract cluster name and namespace from directory name %s. '
        'Directory name convention must be <cluster_name>:<namespace>',
        dirname
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
def file_lock_context(filepath='/tmp/discovery-infra.lock', timeout=300):
    logging.getLogger('filelock').setLevel(logging.ERROR)

    lock = filelock.FileLock(filepath, timeout)
    try:
        lock.acquire()
    except filelock.Timeout:
        log.info(
            'Deleting lock file: %s '
            'since it exceeded timeout of: %d seconds',
            filepath, timeout
        )
        os.unlink(filepath)
        lock.acquire()

    try:
        yield
    finally:
        lock.release()

def _get_hosts_from_network(net):
    desc = md.parseString(net.XMLDesc())
    try:
        hosts = desc.getElementsByTagName("network")[0].getElementsByTagName("ip")[0].getElementsByTagName("dhcp")[0].getElementsByTagName("host")
        return list(map(lambda host: {"mac": host.getAttribute("mac"), "ipaddr": host.getAttribute("ip"), "hostname": host.getAttribute("name")}, hosts))
    except IndexError:
        return []

def _merge(leases, hosts):
    lips = [l["ipaddr"] for l in leases]
    ret = leases + [h for h in hosts if h["ipaddr"] not in lips]
    return ret


def get_network_leases(network_name):
    with file_lock_context():
        net = conn.networkLookupByName(network_name)
        leases =  net.DHCPLeases() # TODO: getting the information from the XML dump until dhcp-leases bug is fixed
        hosts = _get_hosts_from_network(net)
        return _merge(leases, hosts)


def create_ip_address_list(node_count, starting_ip_addr):
    return [str(ipaddress.ip_address(starting_ip_addr) + i) for i in range(node_count)]


def create_ip_address_nested_list(node_count, starting_ip_addr):
    return [[str(ipaddress.ip_address(starting_ip_addr) + i)] for i in range(node_count)]


def create_empty_nested_list(node_count):
    return [[] for i in range(node_count)]


def set_hosts_roles_based_on_requested_name(client, cluster_id):
    hosts = client.get_cluster_hosts(cluster_id=cluster_id)
    hosts_with_roles = []

    for host in hosts:
        role = consts.NodeRoles.MASTER if "master" in host["requested_hostname"] else consts.NodeRoles.WORKER
        hosts_with_roles.append({"id": host["id"], "role": role})
    
    client.update_hosts(cluster_id=cluster_id, hosts_with_roles=hosts_with_roles)


def get_env(env, default=None):
    res = os.environ.get(env, "").strip()
    if not res or res == '""':
        res = default
    return res


def touch(path):
    with open(path, 'a'):
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
            logging.info("Updated /etc/hosts: %s", api_vip_dnsname)


def run_container(container_name, image, flags=[]):
    logging.info(f'Running Container {container_name}')
    run_container_cmd = f'podman {consts.PODMAN_FLAGS} run --name {container_name}'
    
    for flag in flags:
        run_container_cmd += f' {flag}'

    run_container_cmd += f' {image}'

    run_command(run_container_cmd, shell=True)


def remove_running_container(container_name):
    logging.info(f'Removing Container {container_name}')
    container_rm_cmd = f'podman {consts.PODMAN_FLAGS} stop {container_name} && podman {consts.PODMAN_FLAGS} rm {container_name}'
    run_command(container_rm_cmd, shell=True)


def get_openshift_version():
    release_image = os.getenv('OPENSHIFT_INSTALL_RELEASE_IMAGE')

    if release_image:
        f = tempfile.NamedTemporaryFile(mode='w', delete=False)
        f.write(os.getenv('PULL_SECRET'))
        f.close()
        try:
            stdout, _, _ = run_command(f"oc adm release info '{release_image}' --registry-config '{f.name}' -o json | jq -r '.metadata.version' | grep -oP '\\d\\.\\d+'", shell=True)
        finally:
            os.unlink(f.name)
        return stdout

    return get_env('OPENSHIFT_VERSION', consts.DEFAULT_OPENSHIFT_VERSION)


def copy_template_tree(dst, none_platform_mode=False):
    copy_tree(
        src=consts.TF_TEMPLATE_NONE_PLATFORM_FLOW
        if none_platform_mode else
        consts.TF_TEMPLATE_BARE_METAL_FLOW,
        dst=dst
    )
