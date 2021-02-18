import contextlib
import ipaddress
import json
import logging
import random
import time
from collections import Counter
from typing import List

import requests
import waiting
import yaml
from assisted_service_client import models
from netaddr import IPNetwork, IPAddress
from test_infra import consts, utils
from test_infra.tools import static_ips
from tests.conftest import env_variables


class Cluster:

    def __init__(self, api_client, cluster_name=None, additional_ntp_source=None,
                 openshift_version="4.6", cluster_id=None, user_managed_networking=False,
                 high_availability_mode=consts.HighAvailabilityMode.FULL):
        self.api_client = api_client

        self._high_availability_mode = high_availability_mode
        if cluster_id:
            self.id = cluster_id
        else:
            cluster_name = cluster_name or env_variables.get('cluster_name', "test-infra-cluster")
            self.id = self._create(cluster_name, additional_ntp_source, openshift_version,
                                   user_managed_networking=user_managed_networking,
                                   high_availability_mode=high_availability_mode).id
            self.name = cluster_name

    def _create(self,
                cluster_name,
                additional_ntp_source,
                openshift_version,
                user_managed_networking,
                high_availability_mode):
        return self.api_client.create_cluster(
            cluster_name,
            ssh_public_key=env_variables['ssh_public_key'],
            openshift_version=openshift_version,
            pull_secret=env_variables['pull_secret'],
            base_dns_domain=env_variables['base_domain'],
            vip_dhcp_allocation=env_variables['vip_dhcp_allocation'],
            additional_ntp_source=additional_ntp_source,
            user_managed_networking=user_managed_networking,
            high_availability_mode=high_availability_mode
        )

    def delete(self):
        self.api_client.delete_cluster(self.id)

    def get_details(self):
        return self.api_client.cluster_get(self.id)

    def get_cluster_name(self):
        return self.get_details().name

    def get_hosts(self):
        return self.api_client.get_cluster_hosts(self.id)

    def get_host_ids(self):
        return [host["id"] for host in self.get_hosts()]

    def get_host_ids_names_mapping(self):
        return {host["id"]: host["requested_hostname"] for host in self.get_hosts()}

    def get_host_assigned_roles(self):
        hosts = self.get_hosts()
        return {h["id"]: h["role"] for h in hosts}

    def generate_image(self, ssh_key=env_variables['ssh_public_key']):
        self.api_client.generate_image(cluster_id=self.id, ssh_key=ssh_key)

    def generate_and_download_image(
            self,
            iso_download_path=env_variables['iso_download_path'],
            ssh_key=env_variables['ssh_public_key'],
            static_ips=None,
            iso_image_type=env_variables['iso_image_type']
    ):
        self.api_client.generate_and_download_image(
            cluster_id=self.id,
            ssh_key=ssh_key,
            image_path=iso_download_path,
            image_type=iso_image_type,
            static_ips=static_ips,
        )

    def wait_until_hosts_are_disconnected(self, nodes_count=env_variables['num_nodes']):
        statuses = [consts.NodesStatus.DISCONNECTED]
        utils.wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count,
            statuses=statuses,
            timeout=consts.DISCONNECTED_TIMEOUT
        )

    def wait_until_hosts_are_discovered(self, nodes_count=env_variables['num_nodes'],
                                        allow_insufficient=False):
        statuses = [consts.NodesStatus.PENDING_FOR_INPUT, consts.NodesStatus.KNOWN]
        if allow_insufficient:
            statuses.append(consts.NodesStatus.INSUFFICIENT)
        utils.wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count,
            statuses=statuses,
            timeout=consts.NODES_REGISTERED_TIMEOUT
        )

    def _get_matching_hosts(self, host_type, count):
        hosts = self.get_hosts()
        return [{"id": h["id"], "role": host_type}
                for h in hosts
                if host_type in h["requested_hostname"]][:count]

    def set_cluster_name(self, cluster_name):
        logging.info(f'Setting Cluster Name:{cluster_name} for cluster: {self.id}')
        self.api_client.update_cluster(self.id, {"name": cluster_name})

    def select_installation_disk(self, hosts_with_disk_paths):
        self.api_client.select_installation_disk(self.id, hosts_with_disk_paths)

    def set_ocs(self, ocs_enabled):
        logging.info(f'Enabling Ocs to:{ocs_enabled} for cluster: {self.id}')
        ocs_operator = {"operators": [{"operator_type": "ocs", "enabled": ocs_enabled}]}
        self.api_client.update_cluster(self.id, ocs_operator)

    def set_host_roles(self, requested_roles=None):
        if requested_roles is None:
            requested_roles = Counter(master=env_variables['num_masters'], worker=env_variables['num_workers'])
        assigned_roles = self._get_matching_hosts(
            host_type=consts.NodeRoles.MASTER,
            count=requested_roles["master"])

        assigned_roles.extend(self._get_matching_hosts(
            host_type=consts.NodeRoles.WORKER,
            count=requested_roles["worker"]))

        self.api_client.update_hosts(
            cluster_id=self.id,
            hosts_with_roles=assigned_roles)

        return assigned_roles

    def set_specific_host_role(self, host, role):
        assignment_role = [{"id": host["id"], "role": role}]
        self.api_client.update_hosts(
            cluster_id=self.id,
            hosts_with_roles=assignment_role)

    def set_network_params(
            self,
            controller,
            vip_dhcp_allocation=env_variables['vip_dhcp_allocation'],
    ):
        self.api_client.update_cluster(self.id, {
            "vip_dhcp_allocation": vip_dhcp_allocation,
            "service_network_cidr": env_variables['service_cidr'],
            "cluster_network_cidr": env_variables['cluster_cidr'],
            "cluster_network_host_prefix": env_variables['host_prefix'],
        })
        if vip_dhcp_allocation or self._high_availability_mode == consts.HighAvailabilityMode.NONE:
            self.set_machine_cidr(controller.get_machine_cidr())
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

    def set_advanced_networking(self, cluster_cidr, service_cidr, cluster_host_prefix):
        logging.info(
            f"Setting Cluster CIDR: {cluster_cidr}, Service CIDR: {service_cidr},"
            f" Cluster Host Prefix: {cluster_host_prefix} for cluster: {self.id}")
        self.api_client.update_cluster(self.id,
                                       {"cluster_network_cidr": cluster_cidr, "service_network_cidr": service_cidr,
                                        "cluster_network_host_prefix": cluster_host_prefix})

    def set_advanced_cluster_cidr(self, cluster_cidr):
        logging.info(f"Setting Cluster CIDR: {cluster_cidr} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"cluster_network_cidr": cluster_cidr})

    def set_advanced_service_cidr(self, service_cidr):
        logging.info(f"Setting Service CIDR: {service_cidr} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"service_network_cidr": service_cidr})

    def set_advanced_cluster_host_prefix(self, cluster_host_prefix):
        logging.info(f"Setting Cluster Host Prefix: {cluster_host_prefix} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"cluster_network_host_prefix": cluster_host_prefix})

    def set_pull_secret(self, pull_secret):
        logging.info(f"Setting pull secret:{pull_secret} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"pull_secret": pull_secret})

    def set_host_name(self, host_id, requested_name):
        logging.info(f"Setting Required Host Name:{requested_name}, for Host ID: {host_id}")
        host_data = {"hosts_names": [{"id": host_id, "hostname": requested_name}]}
        self.api_client.update_cluster(self.id, host_data)

    def set_additional_ntp_source(self, ntp_source: List[str]):
        logging.info(f"Setting Additional NTP source:{ntp_source}")
        if isinstance(ntp_source, List):
            ntp_source_string = ",".join(ntp_source)
        elif isinstance(ntp_source, str):
            ntp_source_string = ntp_source
        else:
            raise TypeError(f"ntp_source must be a string or a list of strings, got: {ntp_source},"
                            f" type: {type(ntp_source)}")
        self.api_client.update_cluster(self.id, {"additional_ntp_source": ntp_source_string})

    def patch_discovery_ignition(self, ignition):
        self.api_client.patch_cluster_discovery_ignition(self.id, ignition)

    def set_proxy_values(self, http_proxy, https_proxy='', no_proxy=''):
        logging.info(f"Setting http_proxy:{http_proxy}, https_proxy:{https_proxy} and no_proxy:{no_proxy} "
                     f"for cluster: {self.id}")
        self.api_client.set_cluster_proxy(self.id, http_proxy, https_proxy, no_proxy)

    def start_install(self):
        self.api_client.install_cluster(cluster_id=self.id)

    def wait_for_installing_in_progress(self, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS],
            nodes_count=nodes_count,
            timeout=consts.INSTALLING_IN_PROGRESS_TIMEOUT
        )

    def wait_for_write_image_to_disk(self, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.WRITE_IMAGE_TO_DISK, consts.HostsProgressStages.REBOOTING],
            nodes_count=nodes_count,
        )

    def wait_for_host_status(self, statuses, nodes_count=1, fall_on_error_status=True):
        utils.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=statuses,
            nodes_count=nodes_count,
            fall_on_error_status=fall_on_error_status
        )

    def wait_for_specific_host_status(self, host, statuses, nodes_count=1):
        utils.wait_till_specific_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            host_name=host.get('requested_hostname'),
            statuses=statuses,
            nodes_count=nodes_count
        )

    def wait_for_cluster_in_error_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.ERROR],
            timeout=consts.ERROR_TIMEOUT
        )

    def wait_for_pending_for_input_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.PENDING_FOR_INPUT],
            timeout=consts.PENDING_USER_ACTION_TIMEOUT
        )

    def wait_for_at_least_one_host_to_boot_during_install(self, nodes_count=1):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.REBOOTING],
            nodes_count=nodes_count
        )

    def wait_for_non_bootstrap_masters_to_reach_configuring_state_during_install(self):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.CONFIGURING],
            nodes_count=env_variables['num_masters'] - 1
        )

    def wait_for_non_bootstrap_masters_to_reach_joined_state_during_install(self):
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.JOINED],
            nodes_count=env_variables['num_masters'] - 1
        )

    def wait_for_hosts_stage(self, stage: str, nodes_count: int = env_variables['num_nodes'], inclusive: bool = True):
        index = consts.all_host_stages.index(stage)
        utils.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=consts.all_host_stages[index:] if inclusive else consts.all_host_stages[index + 1:],
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
        hosts = self.get_hosts_by_role(consts.NodeRoles.WORKER)
        for host in hosts:
            self.disable_host(host)

    def disable_host(self, host):
        host_name = host["requested_hostname"]
        logging.info(f"Going to disable host: {host_name} in cluster: {self.id}")
        self.api_client.disable_host(cluster_id=self.id, host_id=host["id"])

    def enable_host(self, host):
        host_name = host["requested_hostname"]
        logging.info(f"Going to enable host: {host_name} in cluster: {self.id}")
        self.api_client.enable_host(cluster_id=self.id, host_id=host["id"])

    def delete_host(self, host):
        host_id = host["id"]
        logging.info(f"Going to delete host: {host_id} in cluster: {self.id}")
        self.api_client.deregister_host(cluster_id=self.id, host_id=host_id)

    def cancel_install(self):
        self.api_client.cancel_cluster_install(cluster_id=self.id)

    def get_bootstrap_hostname(self):
        hosts = self.get_hosts_by_role(consts.NodeRoles.MASTER)
        for host in hosts:
            if host.get('bootstrap'):
                logging.info("Bootstrap node is: %s", host["requested_hostname"])
                return host["requested_hostname"]

    def get_hosts_by_role(self, role, hosts=None):
        hosts = hosts or self.api_client.get_cluster_hosts(self.id)
        nodes_by_role = []
        for host in hosts:
            if host["role"] == role:
                nodes_by_role.append(host)
        logging.info(f"Found hosts: {nodes_by_role}, that has the role: {role}")
        return nodes_by_role

    def get_random_host_by_role(self, role):
        return random.choice(self.get_hosts_by_role(role))

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
            timeout=consts.PENDING_USER_ACTION_TIMEOUT
        )

    def wait_for_hosts_to_be_in_wrong_boot_order(
            self,
            nodes_count=env_variables['num_nodes'],
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
            fall_on_error_status=True
    ):
        utils.wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            nodes_count=nodes_count,
            timeout=timeout,
            fall_on_error_status=fall_on_error_status
        )

    def wait_for_ready_to_install(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY],
            timeout=consts.READY_TIMEOUT
        )
        # This code added due to BZ:1909997, temporarily checking if help to prevent unexpected failure
        time.sleep(90)
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY],
            timeout=consts.READY_TIMEOUT
        )

    def is_in_cancelled_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.CANCELLED]
        )

    def is_finalizing(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.FINALIZING]
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
            timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
            fall_on_error_status=True
    ):
        utils.wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            nodes_count=nodes_count,
            timeout=timeout,
            fall_on_error_status=fall_on_error_status,
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
            iso_image_type=env_variables['iso_image_type'],
            ssh_key=env_variables['ssh_public_key'],
            nodes_count=env_variables['num_nodes'],
            vip_dhcp_allocation=env_variables['vip_dhcp_allocation'],
            download_image=True
    ):
        if download_image:
            if env_variables.get('static_ips_config'):
                static_ips_config = static_ips.generate_static_ips_data_from_tf(nodes.controller.tf_folder)
            else:
                static_ips_config = None

            self.generate_and_download_image(
                iso_download_path=iso_download_path,
                iso_image_type=iso_image_type,
                ssh_key=ssh_key,
                static_ips=static_ips_config
            )
        nodes.start_all()
        self.wait_until_hosts_are_discovered(nodes_count=nodes_count, allow_insufficient=True)
        nodes.set_hostnames(self)
        if self._high_availability_mode != consts.HighAvailabilityMode.NONE:
            self.set_host_roles()
        else:
            nodes.set_single_node_ip(self)
        self.set_network_params(
            controller=nodes.controller,
            vip_dhcp_allocation=vip_dhcp_allocation,
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

    def download_installation_logs(self, cluster_tar_path):
        self.api_client.download_cluster_logs(self.id, cluster_tar_path)

    def get_install_config(self):
        return yaml.safe_load(self.api_client.get_cluster_install_config(self.id))

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
        logging.info("Wait until cluster %s validation %s is in status %s",
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
        except BaseException:
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
        except BaseException:
            logging.exception("Failed to get cluster %s validation info", self.id)

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
        except BaseException:
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
        except BaseException:
            logging.exception("Failed to get cluster %s validation info", self.id)

    def wait_for_cluster_to_be_in_installing_pending_user_action_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING_PENDING_USER_ACTION],
            timeout=consts.PENDING_USER_ACTION_TIMEOUT
        )

    def wait_for_cluster_to_be_in_installing_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING],
            timeout=consts.START_CLUSTER_INSTALLATION_TIMEOUT
        )

    @classmethod
    def reset_cluster_and_wait_for_ready(cls, cluster, nodes):
        # Reset cluster install
        cluster.reset_install()
        assert cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        cluster.reboot_required_nodes_into_iso_after_reset(nodes=nodes)
        # Wait for hosts to be rediscovered
        cluster.wait_until_hosts_are_discovered()
        cluster.wait_for_ready_to_install()

    def get_events(self, host_id=''):
        return self.api_client.get_events(cluster_id=self.id, host_id=host_id)

    def _find_event(self, event_to_find, reference_time, params_list, host_id):
        events_list = self.get_events(host_id=host_id)
        for event in events_list:
            if event_to_find in event['message']:
                # Adding a 2 sec buffer to account for a small time diff between the machine and the time on staging
                if utils.to_utc(event['event_time']) >= reference_time - 2:
                    if all(param in event['message'] for param in params_list):
                        # event_exist = True
                        logging.info(f"Event to find: {event_to_find} exists with its params")
                        return True
        else:
            return False

    def wait_for_event(self, event_to_find, reference_time, params_list=None, host_id='', timeout=10):
        logging.info(f"Searching for event: {event_to_find}")
        if params_list is None:
            params_list = list()
        try:
            waiting.wait(
                lambda: self._find_event(
                    event_to_find,
                    reference_time,
                    params_list,
                    host_id
                ),
                timeout_seconds=timeout,
                sleep_seconds=2,
                waiting_for="Event: %s" % event_to_find,
            )
        except waiting.exceptions.TimeoutExpired:
            logging.error(f"Event: {event_to_find} did't found")
            raise

    @staticmethod
    def get_inventory_host_nics_data(host: dict, ipv4_first=True):
        def get_network_interface_ip(interface):
            addresses = interface.ipv4_addresses + interface.ipv6_addresses if ipv4_first else \
                interface.ipv6_addresses + interface.ipv4_addresses
            return addresses[0].split("/")[0] if len(addresses) > 0 else None

        inventory = models.Inventory(**json.loads(host["inventory"]))
        interfaces_list = [models.Interface(**interface) for interface in inventory.interfaces]
        return [{'name': interface.name, 'model': interface.product, 'mac': interface.mac_address,
                 'ip': get_network_interface_ip(interface), 'speed': interface.speed_mbps} for interface in
                interfaces_list]

    @staticmethod
    def get_ip_for_single_node(client, cluster_id, machine_cidr, ipv4_first=True):
        cluster_info = client.cluster_get(cluster_id).to_dict()
        if len(cluster_info["hosts"]) == 0:
            raise Exception("No host found")
        network = IPNetwork(machine_cidr)
        interfaces = Cluster.get_inventory_host_nics_data(cluster_info["hosts"][0], ipv4_first=ipv4_first)
        for intf in interfaces:
            ip = intf["ip"]
            if IPAddress(ip) in network:
                return ip
        raise Exception("IP for single node IPv6 not found")

    def get_host_disks(self, host, filter=None):
        hosts = self.get_hosts()
        selected_host = [h for h in hosts if h["id"] == host["id"]]
        disks = json.loads(selected_host[0]["inventory"])["disks"]
        if not filter:
            return [disk for disk in disks]
        else:
            return [disk for disk in disks if filter(disk)]

    def get_inventory_host_ips_data(self, host: dict):
        nics = self.get_inventory_host_nics_data(host)
        return [nic["ip"] for nic in nics]

    # needed for None platform and single node
    # we need to get ip where api is running
    def get_kube_api_ip(self, hosts):
        for host in hosts:
            for ip in self.get_inventory_host_ips_data(host):
                if self.is_kubeapi_service_ready(ip):
                    return ip

    def get_api_vip(self, cluster):
        cluster = cluster or self.get_details()
        api_vip = cluster.api_vip

        if not api_vip and cluster.user_managed_networking:
            logging.info("API VIP is not set, searching for api ip on masters")
            masters = self.get_hosts_by_role(consts.NodeRoles.MASTER, hosts=cluster.to_dict()["hosts"])
            api_vip = self._wait_for_api_vip(masters)

        logging.info("api vip is %s", api_vip)
        return api_vip

    def _wait_for_api_vip(self, hosts, timeout=180):
        """Enable some grace time for waiting for API's availability."""
        return waiting.wait(lambda: self.get_kube_api_ip(hosts=hosts),
                            timeout_seconds=timeout,
                            sleep_seconds=5,
                            waiting_for="API's IP")

    @staticmethod
    def is_kubeapi_service_ready(ip_or_dns):
        """Validate if kube-api is ready on given address."""
        with contextlib.suppress(ValueError):
            # IPv6 addresses need to be surrounded with square-brackets
            # to differentiate them from domain names
            if ipaddress.ip_address(ip_or_dns).version == 6:
                ip_or_dns = f"[{ip_or_dns}]"

        try:
            response = requests.get(f'https://{ip_or_dns}:6443/readyz',
                                    verify=False,
                                    timeout=1)
            return response.ok
        except BaseException:
            return False


def get_api_vip_from_cluster(api_client, cluster_info: models.cluster.Cluster):
    if isinstance(cluster_info, dict):
        cluster_info = models.cluster.Cluster(**cluster_info)
    cluster = Cluster(api_client=api_client, cluster_id=cluster_info.id)
    return cluster.get_api_vip(cluster=cluster_info)
