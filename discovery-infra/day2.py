import os
import json
import ipaddress
import time
import subprocess
import waiting
import uuid

from test_infra import assisted_service_api, utils, consts
from test_infra.tools import static_ips, terraform_utils
from logger import log


def set_cluster_pull_secret(client, cluster_id, pull_secret):
    client.set_pull_secret(cluster_id, pull_secret)


def execute_day2_cloud_flow(cluster_id, args, has_ipv4):
    execute_day2_flow(cluster_id, args, "cloud", has_ipv4)


def execute_day2_ocp_flow(cluster_id, args, has_ipv4):
    execute_day2_flow(cluster_id, args, "ocp", has_ipv4)

def execute_day2_flow(cluster_id, args, day2_type_flag, has_ipv4):
    utils.recreate_folder(consts.IMAGE_FOLDER, force_recreate=False)
    client = assisted_service_api.create_client(
            url=utils.get_assisted_service_url_by_args(args=args)
    )
    cluster = client.cluster_get(cluster_id=cluster_id)
    cluster_name = cluster.name
    openshift_version = cluster.openshift_version
    api_vip_dnsname = "api." + cluster_name + "." + cluster.base_dns_domain
    api_vip_ip = cluster.api_vip
    terraform_cluster_dir_prefix = cluster_name
    if day2_type_flag == "ocp":
        terraform_cluster_dir_prefix = "test-infra-cluster-assisted-installer"
    else:
        cluster_id = str(uuid.uuid4())
        copy_proxy_from_cluster = cluster
        cluster = client.create_day2_cluster(
            cluster_name + "-day2", cluster_id, **_day2_cluster_create_params(openshift_version, api_vip_dnsname)
        )
        set_cluster_pull_secret(client, cluster_id, args.pull_secret)
        set_cluster_proxy(client, cluster_id, copy_proxy_from_cluster, args)

    config_etc_hosts(api_vip_ip, api_vip_dnsname)
    image_path = os.path.join(
            consts.IMAGE_FOLDER,
            f'{args.namespace}-installer-image.iso'
        )
    client.generate_and_download_image(
            cluster_id=cluster.id,
            image_path=image_path,
            ssh_key=args.ssh_key,
            )

    day2_nodes_flow(
        client,
        terraform_cluster_dir_prefix,
        cluster,
        has_ipv4,
        args.number_of_day2_workers,
        api_vip_ip,
        api_vip_dnsname,
        args.namespace,
        args.install_cluster,
        day2_type_flag
    )


def day2_nodes_flow(client,
                    terraform_cluster_dir_prefix,
                    cluster,
                    has_ipv_4,
                    num_worker_nodes,
                    api_vip_ip,
                    api_vip_dnsname,
                    namespace,
                    install_cluster_flag,
                    day2_type_flag):
    tf_network_name, total_num_nodes = apply_day2_tf_configuration(terraform_cluster_dir_prefix, num_worker_nodes, api_vip_ip, api_vip_dnsname, namespace)
    with utils.file_lock_context():
        utils.run_command(
            f'make _apply_terraform CLUSTER_NAME={terraform_cluster_dir_prefix}'
        )
    time.sleep(5)

    if day2_type_flag == "ocp":
        num_nodes_to_wait = total_num_nodes
        installed_status = consts.NodesStatus.INSTALLED
    else:
        num_nodes_to_wait = num_worker_nodes
        installed_status = consts.NodesStatus.DAY2_INSTALLED

    utils.wait_till_nodes_are_ready(
        nodes_count=num_nodes_to_wait, network_name=tf_network_name
    )

    waiting.wait(
        lambda: utils.are_libvirt_nodes_in_cluster_hosts(
            client, cluster.id, num_nodes_to_wait
        ),
        timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
        sleep_seconds=10,
        waiting_for="Nodes to be registered in inventory service",
    )

    if not has_ipv_4:
        log.info("Set hostnames of day2 cluster %s to work around libvirt for Terrafrom not setting hostnames of IPv6-only hosts", cluster.id)
        tf_folder = utils.get_tf_folder(terraform_cluster_dir_prefix, namespace)
        set_hostnames_from_tf(client=client, cluster_id=cluster.id, tf_folder=tf_folder, network_name=tf_network_name)

    utils.wait_till_all_hosts_are_in_status(
        client=client,
        cluster_id=cluster.id,
        nodes_count=num_worker_nodes,
        statuses=[
            consts.NodesStatus.KNOWN
        ],
        interval=30,
    )

    if install_cluster_flag:
        log.info("Start installing all known nodes in the cluster %s", cluster.id)
        ocp_orig_ready_nodes = get_ocp_cluster_ready_nodes_num()
        hosts = client.get_cluster_hosts(cluster.id)
        [client.install_day2_host(cluster.id, host['id']) for host in hosts if host["status"] == 'known']

        log.info("Start waiting until all nodes of cluster %s have been installed( reached added-to-existing-clustertate)",  cluster.id)
        utils.wait_till_all_hosts_are_in_status(
            client=client,
            cluster_id=cluster.id,
            nodes_count=num_nodes_to_wait,
            statuses=[
                installed_status
            ],
            interval=30,
        )

        log.info("Start waiting until installed nodes has actually been added to the OCP cluster")
        waiting.wait(
            lambda: wait_nodes_join_ocp_cluster(ocp_orig_ready_nodes, num_worker_nodes, day2_type_flag),
            timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
            sleep_seconds=30,
            waiting_for="Day2 nodes to be added to OCP cluster",
        )
        log.info("%d worker nodes were successfully added to OCP cluster", num_worker_nodes)

def set_hostnames_from_tf(client, cluster_id, tf_folder, network_name):
    tf = terraform_utils.TerraformUtils(working_dir=tf_folder)
    libvirt_nodes = utils.extract_nodes_from_tf_state(tf.get_state(), (network_name), consts.NodeRoles.WORKER)
    utils.update_hosts(client, cluster_id, libvirt_nodes, update_roles=False, update_hostnames=True)


def apply_day2_tf_configuration(cluster_name, num_worker_nodes, api_vip_ip, api_vip_dnsname, namespace):
    tf_folder = utils.get_tf_folder(cluster_name, namespace)
    configure_terraform(tf_folder, num_worker_nodes, api_vip_ip, api_vip_dnsname)
    return get_network_nodes_from_terraform(tf_folder)


def configure_terraform(tf_folder, num_worker_nodes, api_vip_ip, api_vip_dnsname):
    tfvars = utils.get_tfvars(tf_folder)
    configure_terraform_workers_nodes(tfvars, num_worker_nodes)
    configure_terraform_api_dns(tfvars, api_vip_ip, api_vip_dnsname)
    utils.set_tfvars(tf_folder, tfvars)


def configure_terraform_workers_nodes(tfvars, num_worker_nodes):
    num_workers = tfvars['worker_count'] + num_worker_nodes
    tfvars['worker_count'] = num_workers
    set_workers_addresses_by_type(tfvars, num_worker_nodes, 'libvirt_master_ips', 'libvirt_worker_ips', 'libvirt_worker_macs')
    set_workers_addresses_by_type(tfvars, num_worker_nodes, 'libvirt_secondary_master_ips', 'libvirt_secondary_worker_ips', 'libvirt_secondary_worker_macs')


def configure_terraform_api_dns(tfvars, api_vip_ip, api_vip_dnsname):
    tfvars['api_vip'] = api_vip_ip


def get_network_nodes_from_terraform(tf_folder):
    tfvars = utils.get_tfvars(tf_folder)
    return tfvars['libvirt_network_name'], tfvars['master_count'] + tfvars['worker_count']


def set_workers_addresses_by_type(tfvars, num_worker_nodes, master_ip_type, worker_ip_type, worker_mac_type):

    old_worker_ips_list = tfvars[worker_ip_type]
    last_master_addresses = tfvars[master_ip_type][-1]

    if last_master_addresses:
        if old_worker_ips_list:
            worker_starting_ip = ipaddress.ip_address(old_worker_ips_list[-1][0])
        else:
            worker_starting_ip = ipaddress.ip_address(last_master_addresses[0])

        worker_ips_list = old_worker_ips_list + utils.create_ip_address_nested_list(num_worker_nodes, worker_starting_ip + 1)
    else:
        log.info("IPv6-only environment. IP addresses are left empty and will be allocated by libvirt DHCP because of a bug in Terraform plugin")
        worker_ips_list = old_worker_ips_list + utils.create_empty_nested_list(num_worker_nodes)

    tfvars[worker_ip_type] = worker_ips_list

    old_worker_mac_addresses = tfvars[worker_mac_type]
    tfvars[worker_mac_type] = old_worker_mac_addresses + static_ips.generate_macs(num_worker_nodes)


def wait_nodes_join_ocp_cluster(num_orig_nodes, num_new_nodes, day2_type_flag):
    if day2_type_flag == "cloud":
        approve_workers_on_ocp_cluster()
    return get_ocp_cluster_ready_nodes_num() == num_orig_nodes + num_new_nodes


def approve_workers_on_ocp_cluster():
    csrs = get_ocp_cluster_csrs()
    for csr in csrs:
        if not csr['status']:
            csr_name = csr['metadata']['name']
            ocp_cluster_csr_approve(csr_name)
            log.info("CSR %s for node %s has been approved", csr_name, csr['spec']['username'])



def config_etc_hosts(api_vip_ip, api_vip_dnsname):
    with open("/etc/hosts", "r") as f:
        hosts_lines = f.readlines()
    for i, line in enumerate(hosts_lines):
        if api_vip_dnsname in line:
            hosts_lines[i] = api_vip_ip + " " + api_vip_dnsname +"\n"
            break
    else:
        hosts_lines.append(api_vip_ip + " " + api_vip_dnsname +"\n")
    with open("/etc/hosts", "w") as f:
        f.writelines(hosts_lines)


def get_ocp_cluster_nodes():
    res = subprocess.check_output("oc --kubeconfig=build/kubeconfig get nodes --output=json", shell=True)
    return json.loads(res)['items']


def is_ocp_node_ready(node_status):
    if not node_status:
        return False
    for condition in node_status['conditions']:
        if condition['status'] == 'True' and condition['type'] == 'Ready':
            return True
    return False


def get_ocp_cluster_ready_nodes_num():
    nodes = get_ocp_cluster_nodes()
    return len([node for node in nodes if is_ocp_node_ready(node['status'])])


def get_ocp_cluster_csrs():
    res = subprocess.check_output("oc --kubeconfig=build/kubeconfig get csr --output=json", shell=True)
    return json.loads(res)['items']


def ocp_cluster_csr_approve(csr_name):
    subprocess.check_output("oc --kubeconfig=build/kubeconfig adm certificate approve %s" % csr_name, shell=True)


def _day2_cluster_create_params(openshift_version, api_vip_dnsname):
    params = {
        "openshift_version": openshift_version,
        "api_vip_dnsname": api_vip_dnsname,
    }
    return params

def set_cluster_proxy(client, cluster_id, copy_proxy_from_cluster, args):
    """
    Set cluster proxy - copy proxy configuration from another (e.g. day 1) cluster,
    or allow setting/overriding it via command arguments
    """
    http_proxy = args.http_proxy if args.http_proxy else copy_proxy_from_cluster.http_proxy
    https_proxy = args.https_proxy if args.https_proxy else copy_proxy_from_cluster.https_proxy
    no_proxy = args.no_proxy if args.no_proxy else copy_proxy_from_cluster.no_proxy
    client.set_cluster_proxy(cluster_id, http_proxy, https_proxy, no_proxy)
