import contextlib
import ipaddress
import json
import os
import random
import re
import time
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import requests
import waiting
import yaml
from assisted_service_client import models
from assisted_service_client.models.operator_type import OperatorType
from junit_report import JunitTestCase
from netaddr import IPAddress, IPNetwork

import consts
from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, ClusterName, exceptions, utils
from assisted_test_infra.test_infra.controllers.load_balancer_controller import LoadBalancerController
from assisted_test_infra.test_infra.controllers.node_controllers import Node
from assisted_test_infra.test_infra.helper_classes.cluster_host import ClusterHost
from assisted_test_infra.test_infra.helper_classes.entity import Entity
from assisted_test_infra.test_infra.helper_classes.events_handler import EventsHandler
from assisted_test_infra.test_infra.helper_classes.infra_env import InfraEnv
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from assisted_test_infra.test_infra.tools import static_network, terraform_utils
from assisted_test_infra.test_infra.utils import logs_utils, network_utils, operators_utils
from assisted_test_infra.test_infra.utils.waiting import wait_till_all_hosts_are_in_status
from service_client import InventoryClient, log


class Cluster(Entity):
    MINIMUM_NODES_TO_WAIT = 1
    EVENTS_THRESHOLD = 500  # TODO - remove EVENTS_THRESHOLD after removing it from kni-assisted-installer-auto

    _config: BaseClusterConfig

    def __init__(
        self,
        api_client: InventoryClient,
        config: BaseClusterConfig,
        infra_env_config: BaseInfraEnvConfig,
        nodes: Optional[Nodes] = None,
    ):
        self._infra_env_config = infra_env_config

        super().__init__(api_client, config, nodes)
        self._infra_env = None

        # Update infraEnv configurations
        self._infra_env_config.cluster_id = config.cluster_id
        self._infra_env_config.openshift_version = self._config.openshift_version
        self._infra_env_config.pull_secret = self._config.pull_secret

        self._high_availability_mode = config.high_availability_mode
        self.name = config.cluster_name.get()

    @property
    def id(self):
        return self._config.cluster_id

    @property
    def kubeconfig_path(self):
        return self._config.kubeconfig_path

    @property
    def iso_download_path(self):
        return self._config.iso_download_path

    @property
    def enable_image_download(self):
        return self._config.download_image

    def _update_existing_cluster_config(self, api_client: InventoryClient, cluster_id: str):
        existing_cluster: models.cluster.Cluster = api_client.cluster_get(cluster_id)

        self.update_config(
            **dict(
                openshift_version=existing_cluster.openshift_version,
                cluster_name=ClusterName(existing_cluster.name),
                additional_ntp_source=existing_cluster.additional_ntp_source,
                user_managed_networking=existing_cluster.user_managed_networking,
                high_availability_mode=existing_cluster.high_availability_mode,
                olm_operators=existing_cluster.monitored_operators,
                base_dns_domain=existing_cluster.base_dns_domain,
                vip_dhcp_allocation=existing_cluster.vip_dhcp_allocation,
            )
        )

    def update_existing(self) -> str:
        log.info(f"Fetching existing cluster with id {self._config.cluster_id}")
        self._update_existing_cluster_config(self.api_client, self._config.cluster_id)
        infra_envs = self.api_client.infra_envs_list()
        for infra_env in infra_envs:
            if infra_env.get("cluster_id") == self._config.cluster_id:
                self._infra_env_config.infra_env_id = infra_env.get("id")
                self._infra_env = InfraEnv(self.api_client, self._infra_env_config, self.nodes)
                break
        return self._config.cluster_id

    def _create(self) -> str:
        disk_encryption = models.DiskEncryption(
            enable_on=self._config.disk_encryption_roles,
            mode=self._config.disk_encryption_mode,
        )

        cluster = self.api_client.create_cluster(
            self._config.cluster_name.get(),
            ssh_public_key=self._config.ssh_public_key,
            openshift_version=self._config.openshift_version,
            pull_secret=self._config.pull_secret,
            base_dns_domain=self._config.base_dns_domain,
            vip_dhcp_allocation=self._config.vip_dhcp_allocation,
            additional_ntp_source=self._config.additional_ntp_source,
            user_managed_networking=self._config.user_managed_networking,
            high_availability_mode=self._config.high_availability_mode,
            olm_operators=[{"name": name} for name in self._config.olm_operators],
            network_type=self._config.network_type,
            disk_encryption=disk_encryption,
        )

        self._config.cluster_id = cluster.id
        return cluster.id

    def delete(self):
        self.deregister_infraenv()
        if self.id:
            self.api_client.delete_cluster(self.id)
            self._config.cluster_id = None

    def deregister_infraenv(self):
        if self._infra_env:
            self._infra_env.deregister()
        self._infra_env = None

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

    def get_operators(self):
        return self.api_client.get_cluster_operators(self.id)

    def get_preflight_requirements(self):
        return self.api_client.get_preflight_requirements(self.id)

    # TODO remove in favor of generate_infra_env
    def generate_image(self):
        warnings.warn("generate_image is deprecated. Use generate_infra_env instead.", DeprecationWarning)
        self.api_client.generate_image(cluster_id=self.id, ssh_key=self._config.ssh_public_key)

    def generate_infra_env(
        self, static_network_config=None, iso_image_type=None, ssh_key=None, ignition_info=None, proxy=None
    ) -> InfraEnv:
        if self._infra_env:
            return self._infra_env

        self._infra_env_config.ssh_public_key = ssh_key or self._config.ssh_public_key
        self._infra_env_config.iso_image_type = iso_image_type or self._config.iso_image_type
        self._infra_env_config.static_network_config = static_network_config
        self._infra_env_config.ignition_config_override = ignition_info
        self._infra_env_config.proxy = proxy or self._config.proxy
        infra_env = InfraEnv(api_client=self.api_client, config=self._infra_env_config)
        self._infra_env = infra_env
        return infra_env

    def update_infra_env_proxy(self, proxy: models.Proxy) -> None:
        self._infra_env_config.proxy = proxy
        self._infra_env.update_proxy(proxy=proxy)

    def download_infra_env_image(self, iso_download_path=None) -> Path:
        iso_download_path = iso_download_path or self._config.iso_download_path
        log.debug(f"Downloading ISO to {iso_download_path}")
        return self._infra_env.download_image(iso_download_path=iso_download_path)

    @JunitTestCase()
    def generate_and_download_infra_env(
        self,
        iso_download_path=None,
        static_network_config=None,
        iso_image_type=None,
        ssh_key=None,
        ignition_info=None,
        proxy=None,
    ) -> Path:
        if self._config.is_static_ip and static_network_config is None:
            static_network_config = static_network.generate_static_network_data_from_tf(self.nodes.controller.tf_folder)

        self.generate_infra_env(
            static_network_config=static_network_config,
            iso_image_type=iso_image_type,
            ssh_key=ssh_key,
            ignition_info=ignition_info,
            proxy=proxy,
        )
        return self.download_infra_env_image(iso_download_path=iso_download_path or self._config.iso_download_path)

    @JunitTestCase()
    def generate_and_download_image(
        self, iso_download_path=None, static_network_config=None, iso_image_type=None, ssh_key=None
    ):
        warnings.warn(
            "generate_and_download_image is deprecated. Use generate_and_download_infra_env instead.",
            DeprecationWarning,
        )
        iso_download_path = iso_download_path or self._config.iso_download_path

        # ensure file path exists before downloading
        if not os.path.exists(iso_download_path):
            utils.recreate_folder(os.path.dirname(iso_download_path), force_recreate=False)

        self.api_client.generate_and_download_image(
            cluster_id=self.id,
            ssh_key=ssh_key or self._config.ssh_public_key,
            image_path=iso_download_path,
            image_type=iso_image_type or self._config.iso_image_type,
            static_network_config=static_network_config,
        )

    def wait_until_hosts_are_disconnected(self, nodes_count: int = None):
        statuses = [consts.NodesStatus.DISCONNECTED]
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count or self.nodes.nodes_count,
            statuses=statuses,
            timeout=consts.DISCONNECTED_TIMEOUT,
        )

    @JunitTestCase()
    def wait_until_hosts_are_discovered(self, allow_insufficient=False, nodes_count: int = None):
        statuses = [consts.NodesStatus.PENDING_FOR_INPUT, consts.NodesStatus.KNOWN]
        if allow_insufficient:
            statuses.append(consts.NodesStatus.INSUFFICIENT)
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count or self.nodes.nodes_count,
            statuses=statuses,
            timeout=consts.NODES_REGISTERED_TIMEOUT,
        )

    def _get_matching_hosts(self, host_type, count):
        hosts = self.get_hosts()
        return [{"id": h["id"], "role": host_type} for h in hosts if host_type in h["requested_hostname"]][:count]

    def set_cluster_name(self, cluster_name: str):
        log.info(f"Setting Cluster Name:{cluster_name} for cluster: {self.id}")
        self.update_config(cluster_name=ClusterName(prefix=cluster_name, suffix=None))
        self.api_client.update_cluster(self.id, {"name": cluster_name})

    def select_installation_disk(self, host_id: str, disk_paths: List[dict]) -> None:
        self._infra_env.select_host_installation_disk(host_id=host_id, disk_paths=disk_paths)

    def set_ocs(self, properties=None):
        self.set_olm_operator(consts.OperatorType.OCS, properties=properties)

    def set_cnv(self, properties=None):
        self.set_olm_operator(consts.OperatorType.CNV, properties=properties)

    def unset_ocs(self):
        self.unset_olm_operator(consts.OperatorType.OCS)

    def unset_cnv(self):
        self.unset_olm_operator(consts.OperatorType.CNV)

    def unset_olm_operator(self, operator_name):
        log.info(f"Unsetting {operator_name} for cluster: {self.id}")
        cluster = self.api_client.cluster_get(self.id)

        olm_operators = []
        for operator in cluster.monitored_operators:
            if operator.name == operator_name or operator.operator_type == OperatorType.BUILTIN:
                continue
            olm_operators.append({"name": operator.name, "properties": operator.properties})

        self.api_client.update_cluster(self.id, {"olm_operators": olm_operators})

    def set_olm_operator(self, operator_name, properties=None):
        log.info(f"Setting {operator_name} for cluster: {self.id}")
        cluster = self.api_client.cluster_get(self.id)

        if operator_name in [o.name for o in cluster.monitored_operators]:
            return

        olm_operators = []
        for operator in cluster.monitored_operators:
            if operator.operator_type == OperatorType.BUILTIN:
                continue
            olm_operators.append({"name": operator.name, "properties": operator.properties})
        olm_operators.append({"name": operator_name, "properties": properties})

        self._config.olm_operators = olm_operators
        self.api_client.update_cluster(self.id, {"olm_operators": olm_operators})

    def set_host_roles(self, num_masters: int = None, num_workers: int = None, requested_roles=None):
        if requested_roles is None:
            requested_roles = Counter(
                master=num_masters or self.nodes.masters_count, worker=num_workers or self.nodes.workers_count
            )
        assigned_roles = self._get_matching_hosts(host_type=consts.NodeRoles.MASTER, count=requested_roles["master"])

        assigned_roles.extend(
            self._get_matching_hosts(host_type=consts.NodeRoles.WORKER, count=requested_roles["worker"])
        )
        for role in assigned_roles:
            self._infra_env.update_host(host_id=role["id"], host_role=role["role"])

        return assigned_roles

    def set_specific_host_role(self, host, role):
        self._infra_env.update_host(host_id=host["id"], host_role=role)

    def set_network_params(self, controller=None):
        # Controller argument is here only for backward compatibility TODO - Remove after QE refactor all e2e tests
        controller = controller or self.nodes.controller  # TODO - Remove after QE refactor all e2e tests

        if self._config.platform == consts.Platforms.NONE:
            log.info("On None platform, leaving network management to the user")
            api_vip = ingress_vip = machine_networks = None

        elif self._config.vip_dhcp_allocation or self._high_availability_mode == consts.HighAvailabilityMode.NONE:
            log.info("Letting access VIPs be deducted from machine networks")
            api_vip = ingress_vip = None
            machine_networks = self.get_machine_networks()

        else:
            log.info("Assigning VIPs statically")
            access_vips = controller.get_ingress_and_api_vips()
            api_vip = access_vips["api_vip"]
            ingress_vip = access_vips["ingress_vip"]
            machine_networks = None

        if self._config.is_ipv4 and self._config.is_ipv6:
            machine_networks = controller.get_all_machine_addresses()

        self.set_advanced_networking(
            vip_dhcp_allocation=self._config.vip_dhcp_allocation,
            cluster_networks=self._config.cluster_networks,
            service_networks=self._config.service_networks,
            machine_networks=machine_networks,
            api_vip=api_vip,
            ingress_vip=ingress_vip,
        )

    def get_primary_machine_cidr(self):
        cidr = self.nodes.controller.get_primary_machine_cidr()

        if not cidr:
            # Support controllers which the machine cidr is not configurable. taking it from the AI instead
            matching_cidrs = self.get_cluster_matching_cidrs(Cluster.get_cluster_hosts(self.get_details()))

            if not matching_cidrs:
                raise RuntimeError("No matching cidr for DHCP")

            cidr = next(iter(matching_cidrs))

        return cidr

    def get_machine_networks(self):
        networks = []

        primary_machine_cidr = self.nodes.controller.get_primary_machine_cidr()
        if primary_machine_cidr:
            networks.append(primary_machine_cidr)

        secondary_machine_cidr = self.nodes.controller.get_provisioning_cidr()
        if secondary_machine_cidr:
            networks.append(secondary_machine_cidr)

        if not networks:
            # Support controllers which the machine cidr is not configurable. taking it from the AI instead
            networks = self.get_cluster_matching_cidrs(Cluster.get_cluster_hosts(self.get_details()))

            if not networks:
                raise RuntimeError("No matching cidr for DHCP")

        return networks

    def set_ingress_and_api_vips(self, vips):
        log.info(f"Setting API VIP:{vips['api_vip']} and ingress VIP:{vips['ingress_vip']} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, vips)

    def set_ssh_key(self, ssh_key: str):
        log.info(f"Setting SSH key:{ssh_key} for cluster: {self.id}")
        self.update_config(ssh_public_key=ssh_key)
        self.api_client.update_cluster(self.id, {"ssh_public_key": ssh_key})

    def set_base_dns_domain(self, base_dns_domain: str):
        log.info(f"Setting base DNS domain:{base_dns_domain} for cluster: {self.id}")
        self.update_config(base_dns_domain=base_dns_domain)
        self.api_client.update_cluster(self.id, {"base_dns_domain": base_dns_domain})

    def set_advanced_networking(
        self,
        vip_dhcp_allocation: Optional[bool] = None,
        cluster_networks: Optional[List[models.ClusterNetwork]] = None,
        service_networks: Optional[List[models.ServiceNetwork]] = None,
        machine_networks: Optional[List[models.MachineNetwork]] = None,
        api_vip: Optional[str] = None,
        ingress_vip: Optional[str] = None,
    ):
        if machine_networks is None:
            machine_networks = self._config.machine_networks
        else:
            machine_networks = [models.MachineNetwork(cidr=cidr) for cidr in machine_networks]

        if vip_dhcp_allocation is None:
            vip_dhcp_allocation = self._config.vip_dhcp_allocation

        advanced_networking = {
            "vip_dhcp_allocation": vip_dhcp_allocation,
            "cluster_networks": cluster_networks if cluster_networks is not None else self._config.cluster_networks,
            "service_networks": service_networks if service_networks is not None else self._config.service_networks,
            "machine_networks": machine_networks,
            "api_vip": api_vip if api_vip is not None else self._config.api_vip,
            "ingress_vip": ingress_vip if ingress_vip is not None else self._config.ingress_vip,
        }

        log.info(f"Updating advanced networking with {advanced_networking} for cluster: {self.id}")

        self.update_config(**advanced_networking)
        self.api_client.update_cluster(self.id, advanced_networking)

    def set_pull_secret(self, pull_secret: str):
        log.info(f"Setting pull secret:{pull_secret} for cluster: {self.id}")
        self.update_config(pull_secret=pull_secret)
        self.api_client.update_cluster(self.id, {"pull_secret": pull_secret})

    def set_host_name(self, host_id, requested_name):
        log.info(f"Setting Required Host Name:{requested_name}, for Host ID: {host_id}")
        self._infra_env.update_host(host_id=host_id, host_name=requested_name)

    def set_additional_ntp_source(self, ntp_source: List[str]):
        log.info(f"Setting Additional NTP source:{ntp_source}")
        if isinstance(ntp_source, List):
            ntp_source_string = ",".join(ntp_source)
        elif isinstance(ntp_source, str):
            ntp_source_string = ntp_source
        else:
            raise TypeError(
                f"ntp_source must be a string or a list of strings, got: {ntp_source}," f" type: {type(ntp_source)}"
            )
        self.update_config(additional_ntp_source=ntp_source_string)
        self.api_client.update_cluster(self.id, {"additional_ntp_source": ntp_source_string})

    def patch_discovery_ignition(self, ignition):
        self._infra_env.patch_discovery_ignition(ignition_info=ignition)

    def set_proxy_values(self, proxy_values: models.Proxy) -> None:
        log.info(f"Setting proxy values {proxy_values} for cluster: {self.id}")
        self.update_config(proxy=proxy_values)
        self.api_client.set_cluster_proxy(
            self.id,
            http_proxy=self._config.proxy.http_proxy,
            https_proxy=self._config.proxy.https_proxy,
            no_proxy=self._config.proxy.no_proxy,
        )

    @JunitTestCase()
    def start_install(self, retries: int = consts.DEFAULT_INSTALLATION_RETRIES_ON_FALLBACK):
        self.api_client.install_cluster(cluster_id=self.id)

        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING, consts.ClusterStatus.READY],
            timeout=consts.ERROR_TIMEOUT,
        )

        if utils.is_cluster_in_status(self.api_client, self.id, [consts.ClusterStatus.READY]):
            if retries > 0:
                log.warning(
                    "An error was occurred during the installation process that caused the cluster to "
                    f"fallback to ready status. Retrying (Attempted left {retries - 1}) ..."
                )
                time.sleep(consts.DURATION_BETWEEN_INSTALLATION_RETRIES)
                return self.start_install(retries - 1)

            raise exceptions.ReturnedToReadyAfterInstallationStartsError()

    def wait_for_logs_complete(self, timeout, interval=60, check_host_logs_only=False):
        logs_utils.wait_for_logs_complete(
            client=self.api_client,
            cluster_id=self.id,
            timeout=timeout,
            interval=interval,
            check_host_logs_only=check_host_logs_only,
        )

    def wait_for_installing_in_progress(self, nodes_count: int = MINIMUM_NODES_TO_WAIT):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS],
            nodes_count=nodes_count,
            timeout=consts.INSTALLING_IN_PROGRESS_TIMEOUT,
        )

    def wait_for_write_image_to_disk(self, nodes_count: int = MINIMUM_NODES_TO_WAIT):
        utils.waiting.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.WRITE_IMAGE_TO_DISK, consts.HostsProgressStages.REBOOTING],
            nodes_count=nodes_count,
        )

    def wait_for_host_status(self, statuses, fall_on_error_status=True, nodes_count: int = MINIMUM_NODES_TO_WAIT):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=statuses,
            nodes_count=nodes_count,
            fall_on_error_status=fall_on_error_status,
        )

    def wait_for_specific_host_status(self, host, statuses, nodes_count: int = MINIMUM_NODES_TO_WAIT):
        utils.waiting.wait_till_specific_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            host_name=host.get("requested_hostname"),
            statuses=statuses,
            nodes_count=nodes_count,
        )

    def wait_for_specific_host_stage(self, host: dict, stage: str, inclusive: bool = True):
        index = consts.all_host_stages.index(stage)
        utils.waiting.wait_till_specific_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            host_name=host.get("requested_hostname"),
            stages=consts.all_host_stages[index:] if inclusive else consts.all_host_stages[index + 1 :],
        )

    def wait_for_cluster_in_error_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.ERROR],
            timeout=consts.ERROR_TIMEOUT,
        )

    def wait_for_pending_for_input_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.PENDING_FOR_INPUT],
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_at_least_one_host_to_boot_during_install(self, nodes_count: int = MINIMUM_NODES_TO_WAIT):
        utils.waiting.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.REBOOTING],
            nodes_count=nodes_count,
        )

    def wait_for_non_bootstrap_masters_to_reach_configuring_state_during_install(self, num_masters: int = None):
        num_masters = num_masters if num_masters is not None else self.nodes.masters_count
        utils.waiting.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.CONFIGURING],
            nodes_count=num_masters - 1,
        )

    def wait_for_non_bootstrap_masters_to_reach_joined_state_during_install(self, num_masters: int = None):
        num_masters = num_masters if num_masters is not None else self.nodes.masters_count
        utils.waiting.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=[consts.HostsProgressStages.JOINED],
            nodes_count=num_masters - 1,
        )

    def wait_for_hosts_stage(self, stage: str, inclusive: bool = True):
        index = consts.all_host_stages.index(stage)
        utils.waiting.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=consts.all_host_stages[index:] if inclusive else consts.all_host_stages[index + 1 :],
            nodes_count=self.nodes.nodes_count,
        )

    @JunitTestCase()
    def start_install_and_wait_for_installed(
        self,
        wait_for_hosts=True,
        wait_for_operators=True,
        wait_for_cluster_install=True,
        download_kubeconfig=True,
    ):
        self.start_install()
        if wait_for_hosts:
            self.wait_for_hosts_to_install()
        if wait_for_operators:
            self.wait_for_operators_to_finish()
        if wait_for_cluster_install:
            self.wait_for_install()
        if download_kubeconfig:
            self.download_kubeconfig()

    def disable_worker_hosts(self):
        hosts = self.get_hosts_by_role(consts.NodeRoles.WORKER)
        for host in hosts:
            self.disable_host(host)

    def disable_host(self, host):
        host_name = host["requested_hostname"]
        log.info(f"Going to disable host: {host_name} in cluster: {self.id}")
        self._infra_env.unbind_host(host_id=host["id"])

    def enable_host(self, host):
        host_name = host["requested_hostname"]
        log.info(f"Going to enable host: {host_name} in cluster: {self.id}")
        self._infra_env.bind_host(host_id=host["id"], cluster_id=self.id)

    def delete_host(self, host):
        host_id = host["id"]
        log.info(f"Going to delete host: {host_id} in cluster: {self.id}")
        self._infra_env.delete_host(host_id=host_id)

    def cancel_install(self):
        self.api_client.cancel_cluster_install(cluster_id=self.id)

    def get_bootstrap_hostname(self):
        hosts = self.get_hosts_by_role(consts.NodeRoles.MASTER)
        for host in hosts:
            if host.get("bootstrap"):
                log.info("Bootstrap node is: %s", host["requested_hostname"])
                return host["requested_hostname"]

    def get_hosts_by_role(self, role, hosts=None):
        hosts = hosts or self.api_client.get_cluster_hosts(self.id)
        nodes_by_role = []
        for host in hosts:
            if host["role"] == role:
                nodes_by_role.append(host)
        log.info(f"Found hosts: {nodes_by_role}, that has the role: {role}")
        return nodes_by_role

    def get_random_host_by_role(self, role):
        return random.choice(self.get_hosts_by_role(role))

    def get_reboot_required_hosts(self):
        return self.api_client.get_hosts_in_statuses(
            cluster_id=self.id, statuses=[consts.NodesStatus.RESETING_PENDING_USER_ACTION]
        )

    def reboot_required_nodes_into_iso_after_reset(self):
        hosts_to_reboot = self.get_reboot_required_hosts()
        self.nodes.run_for_given_nodes_by_cluster_hosts(cluster_hosts=hosts_to_reboot, func_name="reset")

    def wait_for_one_host_to_be_in_wrong_boot_order(self, fall_on_error_status=True):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            status_info=consts.HostStatusInfo.WRONG_BOOT_ORDER,
            fall_on_error_status=fall_on_error_status,
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_at_least_one_host_to_be_in_reboot_timeout(self, fall_on_error_status=True, nodes_count=1):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            status_info=consts.HostStatusInfo.REBOOT_TIMEOUT,
            nodes_count=nodes_count,
            fall_on_error_status=fall_on_error_status,
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_hosts_to_be_in_wrong_boot_order(
        self, nodes_count, timeout=consts.PENDING_USER_ACTION_TIMEOUT, fall_on_error_status=True
    ):
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            status_info=consts.HostStatusInfo.WRONG_BOOT_ORDER,
            nodes_count=nodes_count,
            timeout=timeout,
            fall_on_error_status=fall_on_error_status,
        )

    def wait_for_ready_to_install(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY],
            timeout=consts.READY_TIMEOUT,
        )
        # This code added due to BZ:1909997, temporarily checking if help to prevent unexpected failure
        time.sleep(10)
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY],
            timeout=consts.READY_TIMEOUT,
        )

    def is_in_cancelled_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client, cluster_id=self.id, statuses=[consts.ClusterStatus.CANCELLED]
        )

    def is_in_error(self):
        return utils.is_cluster_in_status(
            client=self.api_client, cluster_id=self.id, statuses=[consts.ClusterStatus.ERROR]
        )

    def is_finalizing(self):
        return utils.is_cluster_in_status(
            client=self.api_client, cluster_id=self.id, statuses=[consts.ClusterStatus.FINALIZING]
        )

    def is_installing(self):
        return utils.is_cluster_in_status(
            client=self.api_client, cluster_id=self.id, statuses=[consts.ClusterStatus.INSTALLING]
        )

    def reset_install(self):
        self.api_client.reset_cluster_install(cluster_id=self.id)

    def is_in_insufficient_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client, cluster_id=self.id, statuses=[consts.ClusterStatus.INSUFFICIENT]
        )

    def wait_for_hosts_to_install(
        self, timeout=consts.CLUSTER_INSTALLATION_TIMEOUT, fall_on_error_status=True, nodes_count: int = None
    ):
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            nodes_count=nodes_count or self.nodes.nodes_count,
            timeout=timeout,
            fall_on_error_status=fall_on_error_status,
        )

    def wait_for_operators_to_finish(self, timeout=consts.CLUSTER_INSTALLATION_TIMEOUT, fall_on_error_status=True):
        operators = self.get_operators()

        if fall_on_error_status:
            statuses = [consts.OperatorStatus.AVAILABLE]
        else:
            statuses = [consts.OperatorStatus.AVAILABLE, consts.OperatorStatus.FAILED]

        operators_utils.wait_till_all_operators_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            operators_count=len(operators_utils.filter_operators_by_type(operators, OperatorType.BUILTIN)),
            operator_types=[OperatorType.BUILTIN],
            statuses=statuses,
            timeout=timeout,
            fall_on_error_status=False,
        )
        operators_utils.wait_till_all_operators_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            operators_count=len(operators_utils.filter_operators_by_type(operators, OperatorType.OLM)),
            operator_types=[OperatorType.OLM],
            statuses=[consts.OperatorStatus.AVAILABLE, consts.OperatorStatus.FAILED],
            timeout=timeout,
            fall_on_error_status=fall_on_error_status,
        )

    def is_operator_in_status(self, operator_name, status):
        return operators_utils.is_operator_in_status(
            operators=self.get_operators(), operator_name=operator_name, status=status
        )

    def wait_for_install(self, timeout=consts.CLUSTER_INSTALLATION_TIMEOUT):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            timeout=timeout,
        )

    def _set_hostnames_and_roles(self):
        cluster_id = self.id
        hosts = self.to_cluster_hosts(self.api_client.get_cluster_hosts(cluster_id))
        nodes = self.nodes.get_nodes(refresh=True)

        for host in hosts:
            if host.has_hostname():
                continue

            name = self.find_matching_node_name(host, nodes)
            assert name is not None, (
                f"Failed to find matching node for host with mac address {host.macs()}"
                f" nodes: {[(n.name, n.ips, n.macs) for n in nodes]}"
            )
            if self.nodes.nodes_count == 1:
                role = None
            else:
                role = consts.NodeRoles.MASTER if consts.NodeRoles.MASTER in name else consts.NodeRoles.WORKER
            self._infra_env.update_host(host_id=host.get_id(), host_role=role, host_name=name)

    def _ha_not_none(self):
        return (
            self._high_availability_mode != consts.HighAvailabilityMode.NONE
            and self._config.platform != consts.Platforms.NONE
        )

    def download_image(self, iso_download_path: str = None) -> Path:
        if self._infra_env is None:
            log.warning("No infra_env found. Generating infra_env and downloading ISO")
            return self.generate_and_download_infra_env(
                iso_download_path=iso_download_path or self._config.iso_download_path,
                iso_image_type=self._config.iso_image_type,
            )
        return self._infra_env.download_image(iso_download_path)

    @JunitTestCase()
    def prepare_for_installation(self, **kwargs):
        super(Cluster, self).prepare_for_installation(**kwargs)

        self.nodes.wait_for_networking()
        self._set_hostnames_and_roles()
        if self._high_availability_mode != consts.HighAvailabilityMode.NONE:
            self.set_host_roles(len(self.nodes.get_masters()), len(self.nodes.get_workers()))

        self.set_network_params(controller=self.nodes.controller)

        # in case of None platform we need to specify dns records before hosts are ready
        if self._config.platform == consts.Platforms.NONE:
            self._configure_load_balancer()
            self.nodes.controller.set_dns_for_user_managed_network()
        elif self._high_availability_mode == consts.HighAvailabilityMode.NONE:
            main_cidr = self.get_primary_machine_cidr()
            ip = Cluster.get_ip_for_single_node(self.api_client, self.id, main_cidr)
            self.nodes.controller.set_single_node_ip(ip)
            self.nodes.controller.set_dns(api_vip=ip, ingress_vip=ip)

        self.wait_for_ready_to_install()

        # in case of regular cluster, need to set dns after vips exits
        # in our case when nodes are ready, vips will be there for sure
        if self._ha_not_none():
            vips_info = self.__class__.get_vips_from_cluster(self.api_client, self.id)
            self.nodes.controller.set_dns(api_vip=vips_info["api_vip"], ingress_vip=vips_info["ingress_vip"])

    def download_kubeconfig_no_ingress(self, kubeconfig_path: str = None):
        self.api_client.download_kubeconfig_no_ingress(self.id, kubeconfig_path or self._config.kubeconfig_path)

    def download_kubeconfig(self, kubeconfig_path: str = None):
        self.api_client.download_kubeconfig(self.id, kubeconfig_path or self._config.kubeconfig_path)

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
            self.id, host_id, step_type=step_type, step_id=step_id, exit_code=exit_code, output=output
        )

    def host_update_install_progress(self, host_id, current_stage, progress_info=None):
        self.api_client.host_update_progress(self.id, host_id, current_stage, progress_info=progress_info)

    def host_complete_install(self):
        self.api_client.complete_cluster_installation(cluster_id=self.id, is_success=True)

    def wait_for_cluster_validation(
        self, validation_section, validation_id, statuses, timeout=consts.VALIDATION_TIMEOUT, interval=2
    ):
        log.info("Wait until cluster %s validation %s is in status %s", self.id, validation_id, statuses)
        try:
            waiting.wait(
                lambda: self.is_cluster_validation_in_status(
                    validation_section=validation_section, validation_id=validation_id, statuses=statuses
                ),
                timeout_seconds=timeout,
                sleep_seconds=interval,
                waiting_for=f"Cluster validation to be in status {statuses}",
            )
        except BaseException:
            log.error(
                "Cluster validation status is: %s",
                utils.get_cluster_validation_value(
                    self.api_client.cluster_get(self.id), validation_section, validation_id
                ),
            )
            raise

    def is_cluster_validation_in_status(self, validation_section, validation_id, statuses):
        log.info("Is cluster %s validation %s in status %s", self.id, validation_id, statuses)
        try:
            return (
                utils.get_cluster_validation_value(
                    self.api_client.cluster_get(self.id), validation_section, validation_id
                )
                in statuses
            )
        except BaseException:
            log.exception("Failed to get cluster %s validation info", self.id)

    def wait_for_host_validation(
        self, host_id, validation_section, validation_id, statuses, timeout=consts.VALIDATION_TIMEOUT, interval=2
    ):
        log.info("Wait until host %s validation %s is in status %s", host_id, validation_id, statuses)
        try:
            waiting.wait(
                lambda: self.is_host_validation_in_status(
                    host_id=host_id,
                    validation_section=validation_section,
                    validation_id=validation_id,
                    statuses=statuses,
                ),
                timeout_seconds=timeout,
                sleep_seconds=interval,
                waiting_for=f"Host validation to be in status {statuses}",
            )
        except BaseException:
            log.error(
                "Host validation status is: %s",
                utils.get_host_validation_value(
                    self.api_client.cluster_get(self.id), host_id, validation_section, validation_id
                ),
            )
            raise

    def is_host_validation_in_status(self, host_id, validation_section, validation_id, statuses):
        log.info("Is host %s validation %s in status %s", host_id, validation_id, statuses)
        try:
            return (
                utils.get_host_validation_value(
                    self.api_client.cluster_get(self.id), host_id, validation_section, validation_id
                )
                in statuses
            )
        except BaseException:
            log.exception("Failed to get cluster %s validation info", self.id)

    def wait_for_cluster_to_be_in_installing_pending_user_action_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING_PENDING_USER_ACTION],
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_cluster_to_be_in_installing_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING],
            timeout=consts.START_CLUSTER_INSTALLATION_TIMEOUT,
        )

    def wait_for_cluster_to_be_in_finalizing_status(self):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.FINALIZING, consts.ClusterStatus.INSTALLED],
            timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
            break_statuses=[consts.ClusterStatus.ERROR],
        )

    def wait_for_cluster_to_be_in_status(self, statuses, timeout=consts.ERROR_TIMEOUT):
        utils.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=statuses,
            timeout=timeout,
        )

    @classmethod
    def reset_cluster_and_wait_for_ready(cls, cluster):
        # Reset cluster install
        cluster.reset_install()
        assert cluster.is_in_insufficient_status()
        # Reboot required nodes into ISO
        cluster.reboot_required_nodes_into_iso_after_reset()
        # Wait for hosts to be rediscovered
        cluster.wait_until_hosts_are_discovered()
        cluster.wait_for_ready_to_install()

    def get_events(self, host_id="", infra_env_id=""):
        warnings.warn(
            "Cluster.get_events is now deprecated, use EventsHandler.get_events instead",
            PendingDeprecationWarning,
        )
        handler = EventsHandler(self.api_client)
        return handler.get_events(host_id, self.id, infra_env_id)

    def _configure_load_balancer(self):
        main_cidr = self.get_primary_machine_cidr()
        secondary_cidr = self.nodes.controller.get_provisioning_cidr()

        master_ips = self.get_master_ips(self.api_client, self.id, main_cidr) + self.get_master_ips(
            self.api_client, self.id, secondary_cidr
        )
        worker_ips = self.get_worker_ips(self.api_client, self.id, main_cidr)

        load_balancer_ip = str(IPNetwork(main_cidr).ip + 1)

        tf = terraform_utils.TerraformUtils(working_dir=self.nodes.controller.tf_folder)
        lb_controller = LoadBalancerController(tf)
        lb_controller.set_load_balancing_config(load_balancer_ip, master_ips, worker_ips)

    @classmethod
    def _get_namespace_index(cls, libvirt_network_if):
        # Hack to retrieve namespace index - does not exist in tests
        matcher = re.match(r"^tt(\d+)$", libvirt_network_if)
        return int(matcher.groups()[0]) if matcher is not None else 0

    @staticmethod
    def get_inventory_host_nics_data(host: dict, ipv4_first=True):
        def get_network_interface_ip(interface):
            addresses = (
                interface.ipv4_addresses + interface.ipv6_addresses
                if ipv4_first
                else interface.ipv6_addresses + interface.ipv4_addresses
            )
            return addresses[0].split("/")[0] if len(addresses) > 0 else None

        inventory = models.Inventory(**json.loads(host["inventory"]))
        interfaces_list = [models.Interface(**interface) for interface in inventory.interfaces]
        return [
            {
                "name": interface.name,
                "model": interface.product,
                "mac": interface.mac_address,
                "ip": get_network_interface_ip(interface),
                "speed": interface.speed_mbps,
            }
            for interface in interfaces_list
        ]

    @staticmethod
    def get_hosts_nics_data(hosts: list, ipv4_first=True):
        return [Cluster.get_inventory_host_nics_data(h, ipv4_first=ipv4_first) for h in hosts]

    @staticmethod
    def get_cluster_hosts(cluster: models.cluster.Cluster) -> List[ClusterHost]:
        return [ClusterHost(h) for h in cluster.hosts]

    @staticmethod
    def to_cluster_hosts(hosts: List[Dict[str, Any]]) -> List[ClusterHost]:
        return [ClusterHost(models.Host(**h)) for h in hosts]

    def get_cluster_cidrs(self, hosts: List[ClusterHost]) -> Set[str]:
        cidrs = set()

        for host in hosts:
            ips = []
            if self.nodes.is_ipv4:
                ips += host.ipv4_addresses()
            if self.nodes.is_ipv6:
                ips += host.ipv6_addresses()

            for host_ip in ips:
                cidr = network_utils.get_cidr_by_interface(host_ip)
                cidrs.add(cidr)

        return cidrs

    def get_cluster_matching_cidrs(self, hosts: List[ClusterHost]) -> Set[str]:
        cluster_cidrs = self.get_cluster_cidrs(hosts)
        matching_cidrs = set()

        for cidr in cluster_cidrs:
            for host in hosts:
                interfaces = []
                if self.nodes.is_ipv4:
                    interfaces += host.ipv4_addresses()
                if self.nodes.is_ipv6:
                    interfaces += host.ipv6_addresses()

                if not network_utils.any_interface_in_cidr(interfaces, cidr):
                    break

            matching_cidrs.add(cidr)

        return matching_cidrs

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
        raise Exception("IP for single node not found")

    @staticmethod
    def get_ips_for_role(client, cluster_id, network, role):
        cluster_info = client.cluster_get(cluster_id).to_dict()
        ret = []
        net = IPNetwork(network)
        hosts_interfaces = Cluster.get_hosts_nics_data([h for h in cluster_info["hosts"] if h["role"] == role])
        for host_interfaces in hosts_interfaces:
            for intf in host_interfaces:
                ip = IPAddress(intf["ip"])
                if ip in net:
                    ret = ret + [intf["ip"]]
        return ret

    @staticmethod
    def get_master_ips(client, cluster_id, network):
        return Cluster.get_ips_for_role(client, cluster_id, network, consts.NodeRoles.MASTER)

    @staticmethod
    def get_worker_ips(client, cluster_id, network):
        return Cluster.get_ips_for_role(client, cluster_id, network, consts.NodeRoles.WORKER)

    @staticmethod
    def get_vips_from_cluster(client, cluster_id):
        cluster_info = client.cluster_get(cluster_id)
        return dict(api_vip=cluster_info.api_vip, ingress_vip=cluster_info.ingress_vip)

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
            log.info("API VIP is not set, searching for api ip on masters")
            masters = self.get_hosts_by_role(consts.NodeRoles.MASTER, hosts=cluster.to_dict()["hosts"])
            api_vip = self._wait_for_api_vip(masters)

        log.info("api vip is %s", api_vip)
        return api_vip

    def _wait_for_api_vip(self, hosts, timeout=180):
        """Enable some grace time for waiting for API's availability."""
        return waiting.wait(
            lambda: self.get_kube_api_ip(hosts=hosts), timeout_seconds=timeout, sleep_seconds=5, waiting_for="API's IP"
        )

    def find_matching_node_name(self, host: ClusterHost, nodes: List[Node]) -> Union[str, None]:
        # Looking for node matches the given host by its mac address (which is unique)
        for node in nodes:
            for mac in node.macs:
                if mac.lower() in host.macs():
                    return node.name

        # IPv6 static ips
        if self._config.is_static_ip:
            mappings = static_network.get_name_to_mac_addresses_mapping(self.nodes.controller.tf_folder)
            for mac in host.macs():
                for name, macs in mappings.items():
                    if mac in macs:
                        return name

        return None

    @staticmethod
    def is_kubeapi_service_ready(ip_or_dns):
        """Validate if kube-api is ready on given address."""
        with contextlib.suppress(ValueError):
            # IPv6 addresses need to be surrounded with square-brackets
            # to differentiate them from domain names
            if ipaddress.ip_address(ip_or_dns).version == 6:
                ip_or_dns = f"[{ip_or_dns}]"

        try:
            response = requests.get(f"https://{ip_or_dns}:6443/readyz", verify=False, timeout=1)
            return response.ok
        except BaseException:
            return False

    def wait_and_kill_installer(self, host):
        # Wait for specific host to be in installing in progress
        self.wait_for_specific_host_status(host=host, statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS])
        # Kill installer to simulate host error
        selected_node = self.nodes.get_node_from_cluster_host(host)
        selected_node.kill_installer()


def get_api_vip_from_cluster(api_client, cluster_info: Union[dict, models.cluster.Cluster], pull_secret):
    import warnings

    from tests.config import ClusterConfig, InfraEnvConfig

    warnings.warn(
        "Soon get_api_vip_from_cluster will be deprecated. Avoid using or adding new functionality to "
        "this function. The function and solution for that case have not been determined yet. It might be "
        "on another module, or as a classmethod within Cluster class."
        " For more information see https://issues.redhat.com/browse/MGMT-4975",
        PendingDeprecationWarning,
    )

    if isinstance(cluster_info, dict):
        cluster_info = models.cluster.Cluster(**cluster_info)
    cluster = Cluster(
        api_client=api_client,
        infra_env_config=InfraEnvConfig(),
        config=ClusterConfig(
            cluster_name=ClusterName(cluster_info.name),
            pull_secret=pull_secret,
            ssh_public_key=cluster_info.ssh_public_key,
            cluster_id=cluster_info.id,
        ),
        nodes=None,
    )
    return cluster.get_api_vip(cluster=cluster_info)
