import logging
import waiting
import yaml
from collections import Counter

from tests.conftest import env_variables
from test_infra import consts, utils


class Cluster:
    
    def __init__(self, api_client, cluster_name, cluster_id=None):
        self.api_client = api_client

        if cluster_id:
            self.id = cluster_id
        else:
            self.id = self._create(cluster_name).id
    
    def _create(self, cluster_name):
        return self.api_client.create_cluster(
            cluster_name,
            ssh_public_key=env_variables['ssh_public_key'],
            openshift_version=env_variables['openshift_version'],
            pull_secret=env_variables['pull_secret'],
            base_dns_domain=env_variables['base_domain'],
            vip_dhcp_allocation=env_variables['vip_dhcp_allocation']
        )

    def delete(self):
        self.api_client.delete_cluster(self.id)

    def get_details(self):
        return self.api_client.cluster_get(self.id)

    def get_hosts(self):
        return self.api_client.get_cluster_hosts(self.id)

    def get_host_ids(self):
        return [host["id"] for host in self.get_hosts()]

    def get_host_assigned_roles(self):
        hosts = self.get_hosts()
        return {h["id"]: h["role"] for h in hosts}

    def generate_and_download_image(
        self,
        iso_download_path=env_variables['iso_download_path'],
        ssh_key=env_variables['ssh_public_key']
        ):
        self.api_client.generate_and_download_image(
            cluster_id=self.id,
            ssh_key=ssh_key,
            image_path=iso_download_path
        )

    def wait_until_hosts_are_discovered(self, nodes_count=env_variables['num_nodes'],
        allow_insufficient=False
        ):
        statuses=[consts.NodesStatus.PENDING_FOR_INPUT, consts.NodesStatus.KNOWN]
        if allow_insufficient:
            statuses.append(consts.NodesStatus.INSUFFICIENT)
        utils.wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count,
            statuses=statuses
        )

    def _get_matching_hosts(self, host_type, count):
        hosts = self.get_hosts()
        return [{"id": h["id"], "role": host_type}
                for h in hosts
                if host_type in h["requested_hostname"]][:count]

    def set_host_roles(
        self, 
        requested_roles=Counter(master=env_variables['num_masters'], worker=env_variables['num_workers'])
    ):
        assigned_roles = self._get_matching_hosts(
            host_type=consts.NodeRoles.MASTER,
            count=requested_roles["master"])

        assigned_roles.extend(self._get_matching_hosts(
            host_type=consts.NodeRoles.WORKER,
            count=requested_roles["worker"]))

        self.api_client.set_hosts_roles(
            cluster_id=self.id,
            hosts_with_roles=assigned_roles)

        return assigned_roles

    def set_network_params(
        self, 
        controller,
        nodes_count=env_variables['num_nodes'],
        vip_dhcp_allocation=env_variables['vip_dhcp_allocation'],
        cluster_machine_cidr=env_variables['machine_cidr']
    ):
        if vip_dhcp_allocation:
            self.set_machine_cidr(cluster_machine_cidr)
        else:
            self.set_ingress_and_api_vips(controller.get_ingress_and_api_vips())

    def set_machine_cidr(self, machine_cidr):
        logging.info(f'Setting Machine Network CIDR:{machine_cidr} for cluster: {self.id}')
        self.api_client.update_cluster(self.id, {"machine_network_cidr": machine_cidr})

    def set_ingress_and_api_vips(self, vips):
        logging.info(f"Setting API VIP:{vips['api_vip']} and ingres VIP:{vips['ingress_vip']} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, vips)

    def set_ssh_key(self, ssh_key):
        logging.info(f"Setting SSH key:{ssh_key} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"ssh_public_key": ssh_key})

    def set_base_dns_domain(self, base_dns_domain):
        logging.info(f"Setting base DNS domain:{base_dns_domain} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"base_dns_domain": base_dns_domain})

    def set_pull_secret(self, pull_secret):
        logging.info(f"Setting pull secret:{pull_secret} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"pull_secret": pull_secret})

    def patch_discovery_ignition(self, ignition):
        self.api_client.patch_cluster_discovery_ignition(self.id, ignition)
        
    def set_proxy_values(self, http_proxy, https_proxy='', no_proxy=''):
        logging.info(f"Setting http_proxy:{http_proxy}, https_proxy:{https_proxy} and no_proxy:{no_proxy} for cluster: {self.id}")
        self.api_client.set_cluster_proxy(self.id, http_proxy, https_proxy, no_proxy)

    def start_install(self):
        self.api_client.install_cluster(cluster_id=self.id)

    def wait_for_installing_in_progress(self, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS],
            nodes_count=nodes_count
        )

    def wait_for_write_image_to_disk(self, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.WRITE_IMAGE_TO_DISK],
            nodes_count=nodes_count,
        )

    def wait_for_host_status(self, statuses, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=statuses,
            nodes_count=nodes_count
        )

    def wait_for_cluster_in_error_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.ERROR]
        )

    def wait_for_pending_for_input_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.PENDING_FOR_INPUT]
        )

    def wait_for_at_least_one_host_to_boot_during_install(self, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.REBOOTING],
            nodes_count=nodes_count
        )

    def start_install_and_wait_for_installed(self,
                                             wait_for_hosts=True,
                                             wait_for_cluster_install=True,
                                             nodes_count=env_variables['num_nodes']
                                             ):
        self.start_install()
        if wait_for_hosts:
            self.wait_for_hosts_to_install(nodes_count=nodes_count)
        if wait_for_cluster_install:
            self.wait_for_install()

    def disable_worker_hosts(self):
        hosts = self.api_client.get_cluster_hosts(cluster_id=self.id)
        for host in hosts:
            if host["role"] == consts.NodeRoles.WORKER:
                host_name = host["requested_hostname"]
                logging.info(f"Going to disable host: {host_name} in cluster: {self.id}")
                self.api_client.disable_host(cluster_id=self.id, host_id=host["id"])

    def cancel_install(self):
        self.api_client.cancel_cluster_install(cluster_id=self.id)

    def get_bootstrap_hostname(self):
        hosts = self.get_hosts_by_role(consts.NodeRoles.MASTER)
        for host in hosts:
            if host.get('bootstrap'):
                logging.info("Bootstrap node is: %s", host["requested_hostname"])
                return host["requested_hostname"]

    def get_hosts_by_role(self, role):
        hosts = self.api_client.get_cluster_hosts(self.id)
        nodes_by_role = []
        for host in hosts:
            if host["role"] == role:
                nodes_by_role.append(host)
        logging.info(f"Found hosts: {nodes_by_role}, that has the role: {role}")
        return nodes_by_role

    def get_reboot_required_hosts(self):
        return self.api_client.get_hosts_in_statuses(
            cluster_id=self.id,
            statuses=[consts.NodesStatus.RESETING_PENDING_USER_ACTION]
        )

    def reboot_required_nodes_into_iso_after_reset(self, nodes):
        hosts_to_reboot = self.get_reboot_required_hosts()
        nodes.run_for_given_nodes_by_cluster_hosts(cluster_hosts=hosts_to_reboot, func_name="reset")

    def wait_for_one_host_to_be_in_wrong_boot_order(self, fall_on_error_status=True):
        utils.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            fall_on_error_status=fall_on_error_status,
        )

    def wait_for_ready_to_install(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY]
        )

    def is_in_cancelled_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.CANCELLED]
        )

    def is_installing(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING]
        )

    def reset_install(self):
        self.api_client.reset_cluster_install(cluster_id=self.id)

    def is_in_insufficient_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSUFFICIENT]
        )
    
    def wait_for_hosts_to_install(
        self, 
        nodes_count=env_variables['num_nodes'],
        timeout=consts.CLUSTER_INSTALLATION_TIMEOUT
    ):
        utils.wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            nodes_count=nodes_count,
            timeout=timeout,
        )

    def wait_for_install(
        self,  
        timeout=consts.CLUSTER_INSTALLATION_TIMEOUT
    ):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            timeout=timeout,
        )

    def prepare_for_install(
        self, 
        nodes,
        iso_download_path=env_variables['iso_download_path'],
        ssh_key=env_variables['ssh_public_key'],
        nodes_count=env_variables['num_nodes'],
        vip_dhcp_allocation=env_variables['vip_dhcp_allocation'],
        cluster_machine_cidr=env_variables['machine_cidr']
        ):
        self.generate_and_download_image(
            iso_download_path=iso_download_path,
            ssh_key=ssh_key,
        )
        nodes.start_all()
        self.wait_until_hosts_are_discovered(nodes_count=nodes_count)
        self.set_host_roles()
        self.set_network_params(
            controller=nodes.controller,
            nodes_count=nodes_count,
            vip_dhcp_allocation=vip_dhcp_allocation,
            cluster_machine_cidr=cluster_machine_cidr
        )
        self.wait_for_ready_to_install()

    def download_kubeconfig_no_ingress(
        self, kubeconfig_path=env_variables['kubeconfig_path']
        ):
        self.api_client.download_kubeconfig_no_ingress(self.id, kubeconfig_path)

    def download_kubeconfig(
        self, kubeconfig_path=env_variables['kubeconfig_path']
        ):
        self.api_client.download_kubeconfig(self.id, kubeconfig_path)

    def download_installation_logs(self, path):
        self.api_client.download_cluster_logs(self.id, path)

    def get_install_config(self):
        return yaml.load(self.api_client.get_cluster_install_config(self.id), Loader=yaml.SafeLoader)

    def get_admin_credentials(self):
        return self.api_client.get_cluster_admin_credentials(self.id)

    def register_dummy_host(self):
        dummy_host_id = "b164df18-0ff1-4b85-9121-059f10f58f71"
        self.api_client.register_host(self.id, dummy_host_id)

    def host_get_next_step(self, host_id):
        return self.api_client.host_get_next_step(self.id, host_id)

    def host_post_step_result(self, host_id, step_type, step_id, exit_code, output):
        self.api_client.host_post_step_result(
            self.id, 
            host_id,
            step_type=step_type,
            step_id=step_id,
            exit_code=exit_code,
            output=output
        )

    def host_update_install_progress(self, host_id, current_stage, progress_info=None):
        self.api_client.host_update_progress(
            self.id,
            host_id,
            current_stage,
            progress_info=progress_info
        )

    def host_complete_install(self):
        self.api_client.complete_cluster_installation(cluster_id=self.id, is_success=True)

    def setup_nodes(self, nodes):
        self.generate_and_download_image()
        nodes.start_all()
        self.wait_until_hosts_are_discovered(nodes_count=len(nodes))
        return nodes.create_nodes_cluster_hosts_mapping(cluster=self)

    def wait_for_cluster_validation(
        self, validation_section, validation_id, statuses,
        timeout=consts.VALIDATION_TIMEOUT, interval=2
    ):
        logging.info(f"Wait until cluster %s validation %s is in status %s",
            self.id, validation_id, statuses)
        try:
            waiting.wait(
                lambda: self.is_cluster_validation_in_status(
                    validation_section=validation_section,
                    validation_id=validation_id,
                    statuses=statuses
                ),
                timeout_seconds=timeout,
                sleep_seconds=interval,
                waiting_for="Cluster validation to be in status %s" % statuses,
            )
        except:
            logging.error("Cluster validation status is: %s",
                utils.get_cluster_validation_value(
                    self.api_client.cluster_get(self.id), validation_section,
                        validation_id))
            raise

    def is_cluster_validation_in_status(
        self, validation_section, validation_id, statuses
    ):
        logging.info("Is cluster %s validation %s in status %s",
            self.id, validation_id, statuses)
        try:
            return utils.get_cluster_validation_value(
                self.api_client.cluster_get(self.id),
                validation_section, validation_id) in statuses
        except:
            log.exception("Failed to get cluster %s validation info", self.id)

    def wait_for_host_validation(
        self, host_id, validation_section, validation_id, statuses,
        timeout=consts.VALIDATION_TIMEOUT, interval=2
    ):
        logging.info("Wait until host %s validation %s is in status %s", host_id,
            validation_id, statuses)
        try:
            waiting.wait(
                lambda: self.is_host_validation_in_status(
                    host_id=host_id,
                    validation_section=validation_section,
                    validation_id=validation_id,
                    statuses=statuses
                ),
                timeout_seconds=timeout,
                sleep_seconds=interval,
                waiting_for="Host validation to be in status %s" % statuses,
            )
        except:
            logging.error("Host validation status is: %s",
                utils.get_host_validation_value(self.api_client.cluster_get(self.id),
                host_id, validation_section, validation_id))
            raise

    def is_host_validation_in_status(
            self, host_id, validation_section, validation_id, statuses
    ):
        logging.info("Is host %s validation %s in status %s", host_id, validation_id, statuses)
        try:
            return utils.get_host_validation_value(self.api_client.cluster_get(self.id),
                host_id, validation_section, validation_id) in statuses
        except:
            logging.exception("Failed to get cluster %s validation info", self.id)
