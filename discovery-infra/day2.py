import os
import ipaddress
import time
import utils
import waiting
import uuid
import assisted_service_api
import consts


def set_cluster_pull_secret(client, cluster_id, pull_secret):
    client.set_pull_secret(cluster_id, pull_secret)


def execute_day2_flow(internal_cluster_name, args):
    utils.recreate_folder(consts.IMAGE_FOLDER, force_recreate=False)
    client = assisted_service_api.create_client(
            url=utils.get_assisted_service_url_by_args(args=args)
            )
    cluster_id = str(uuid.uuid4())
    random_postfix = cluster_id[:8]
    ui_cluster_name = internal_cluster_name + f'-{random_postfix}'
    cluster = client.create_day2_cluster(
            ui_cluster_name, cluster_id, **_day2_cluster_create_params(args)
            )

    set_cluster_pull_secret(client, cluster_id, args.pull_secret)

    image_path = os.path.join(
            consts.IMAGE_FOLDER,
            f'{args.namespace}-installer-image.iso'
        )
    client.generate_and_download_image(
            cluster_id=cluster.id,
            image_path=image_path,
            ssh_key=args.ssh_key,
            )

    day2_nodes_flow(client, internal_cluster_name, cluster, image_path, args.number_of_workers, args.api_vip_ip, args.api_vip_dnsname, args.namespace, args.install_cluster)


def day2_nodes_flow(client, cluster_name, cluster, image_path, num_worker_nodes, api_vip_ip, api_vip_dnsname, namespace, install_cluster_flag):
    tf_network_name, total_num_nodes = apply_day2_tf_configuration(cluster_name, num_worker_nodes, api_vip_ip, api_vip_dnsname, namespace)
    with utils.file_lock_context():
        utils.run_command(
            f'make _apply_terraform CLUSTER_NAME={cluster_name}'
        )
    time.sleep(5)

    utils.wait_till_nodes_are_ready(
        nodes_count=total_num_nodes, network_name=tf_network_name
    )

    waiting.wait(
        lambda: utils.are_libvirt_nodes_in_cluster_hosts(
            client, cluster.id, num_worker_nodes
        ),
        timeout_seconds=consts.NODES_REGISTERED_TIMEOUT,
        sleep_seconds=10,
        waiting_for="Nodes to be registered in inventory service",
    )

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
        client.install_day2_cluster(cluster.id)

        utils.wait_till_all_hosts_are_in_status(
            client=client,
            cluster_id=cluster.id,
            nodes_count=num_worker_nodes,
            statuses=[
                consts.NodesStatus.DAY2_INSTALLED
            ],
            interval=30,
        )


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
    set_workers_ips_by_type(tfvars, num_worker_nodes, 'libvirt_master_ips', 'libvirt_worker_ips')
    set_workers_ips_by_type(tfvars, num_worker_nodes, 'libvirt_secondary_master_ips', 'libvirt_secondary_worker_ips')


def configure_terraform_api_dns(tfvars, api_vip_ip, api_vip_dnsname):
    tfvars['api_vip'] = api_vip_ip


def get_network_nodes_from_terraform(tf_folder):
    tfvars = utils.get_tfvars(tf_folder)
    return tfvars['libvirt_network_name'], tfvars['master_count'] + tfvars['worker_count']


def set_workers_ips_by_type(tfvars, num_worker_nodes, master_ip_type, worker_ip_type):
    master_end_ip = tfvars[master_ip_type][-1]
    workers_ip_list = tfvars[worker_ip_type]
    if not workers_ip_list:
        worker_starting_ip = ipaddress.ip_address(master_end_ip)
    else:
        worker_starting_ip = ipaddress.ip_address(tfvars[worker_ip_type][-1])
    worker_ips_list = workers_ip_list + utils.create_ip_address_list(num_worker_nodes, worker_starting_ip + 1)
    tfvars[worker_ip_type] = worker_ips_list


def _day2_cluster_create_params(args):
    params = {
        "openshift_version": args.openshift_version,
        "api_vip_dnsname": args.api_vip_dnsname,
    }
    return params
