import base64
import json
import random
import re
import time
from collections import Counter
from typing import List, Optional, Set

import waiting
import yaml
from assisted_service_client import models
from assisted_service_client.models.api_vip import ApiVip
from assisted_service_client.models.operator_type import OperatorType
from junit_report import JunitTestCase
from netaddr import IPAddress, IPNetwork

import consts
from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, ClusterName, exceptions, utils
from assisted_test_infra.test_infra.controllers.load_balancer_controller import LoadBalancerController
from assisted_test_infra.test_infra.helper_classes.base_cluster import BaseCluster
from assisted_test_infra.test_infra.helper_classes.cluster_host import ClusterHost
from assisted_test_infra.test_infra.helper_classes.infra_env import InfraEnv
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from assisted_test_infra.test_infra.tools import terraform_utils
from assisted_test_infra.test_infra.utils import logs_utils, network_utils, operators_utils, unescape_string
from assisted_test_infra.test_infra.utils.waiting import (
    wait_till_all_hosts_are_in_status,
    wait_till_all_hosts_use_agent_image,
)
from service_client import InventoryClient, log


class Cluster(BaseCluster):
    MINIMUM_NODES_TO_WAIT = 1
    EVENTS_THRESHOLD = 500  # TODO - remove EVENTS_THRESHOLD after removing it from kni-assisted-installer-auto

    def __init__(
        self,
        api_client: InventoryClient,
        config: BaseClusterConfig,
        infra_env_config: BaseInfraEnvConfig,
        nodes: Optional[Nodes] = None,
    ):
        self._is_installed = False

        super().__init__(api_client, config, infra_env_config, nodes)

        self._high_availability_mode = config.high_availability_mode
        self.name = config.cluster_name.get()

    @property
    def kubeconfig_path(self):
        return self._config.kubeconfig_path

    @property
    def iso_download_path(self):
        return self._config.iso_download_path

    @property
    def is_installed(self) -> bool:
        """Returns true when this cluster is installed."""
        return self._is_installed

    @property
    def enable_image_download(self):
        return self._config.download_image

    @property
    def high_availability_mode(self):
        return self._config.high_availability_mode

    def _update_existing_cluster_config(self, api_client: InventoryClient, cluster_id: str):
        existing_cluster: models.cluster.Cluster = api_client.cluster_get(cluster_id)

        self.update_config(
            **dict(
                openshift_version=existing_cluster.openshift_version,
                entity_name=ClusterName(existing_cluster.name),
                additional_ntp_source=existing_cluster.additional_ntp_source,
                user_managed_networking=existing_cluster.user_managed_networking,
                high_availability_mode=existing_cluster.high_availability_mode,
                olm_operators=existing_cluster.monitored_operators,
                base_dns_domain=existing_cluster.base_dns_domain,
                vip_dhcp_allocation=existing_cluster.vip_dhcp_allocation,
                cluster_tags=existing_cluster.tags,
            )
        )

    def update_existing(self) -> str:
        log.info(f"Fetching existing cluster with id {self._config.cluster_id}")
        self._update_existing_cluster_config(self.api_client, self._config.cluster_id)

        # Assuming single or no infra_env - TODO need to change when adding multi-infra_env support to test_infra
        for infra_env in self.api_client.get_infra_envs_by_cluster_id(self.id):
            self._infra_env_config.infra_env_id = infra_env.get("id")
            self._infra_env = InfraEnv(self.api_client, self._infra_env_config, self.nodes)
            log.info(f"Found infra-env {self._infra_env.id} for cluster {self.id}")
            self._is_installed = True
            break
        else:
            log.warning(f"Could not find any infra-env object for cluster ID {self.id}")

        return self._config.cluster_id

    def _create(self) -> str:
        extra_vars = {}

        disk_encryption = models.DiskEncryption(
            enable_on=self._config.disk_encryption_roles,
            mode=self._config.disk_encryption_mode,
            tang_servers=self._config.tang_servers,
        )

        if self._config.platform:
            platform = models.Platform(type=self._config.platform)
            if self._config.platform == consts.Platforms.EXTERNAL:
                platform.external = models.PlatformExternal(
                    platform_name=self._config.external_platform_name,
                    cloud_controller_manager=self._config.external_cloud_controller_manager,
                )
            extra_vars["platform"] = platform

        if self._config.vip_dhcp_allocation is not None:
            extra_vars["vip_dhcp_allocation"] = self._config.vip_dhcp_allocation

        if self._config.network_type is not None:
            extra_vars["network_type"] = self._config.network_type

        if self._config.is_disconnected:
            extra_vars["is_disconnected"] = self._config.is_disconnected

        if self._config.registry_ca_path:
            extra_vars["registry_ca_path"] = self._config.registry_ca_path

        if self.nodes.masters_count and self.nodes.masters_count > 3:
            extra_vars["control_plane_count"] = self.nodes.masters_count

        if self._config.load_balancer_type == consts.LoadBalancerType.USER_MANAGED.value:
            extra_vars["load_balancer"] = {"type": self._config.load_balancer_type}

        if len(self._config.olm_operators) > 0:
            olm_operators = self.get_olm_operators()
            if olm_operators:
                extra_vars["olm_operators"] = olm_operators

        cluster = self.api_client.create_cluster(
            self._config.cluster_name.get(),
            ssh_public_key=self._config.ssh_public_key,
            openshift_version=self._config.openshift_version,
            pull_secret=self._config.pull_secret,
            base_dns_domain=self._config.base_dns_domain,
            additional_ntp_source=self._config.additional_ntp_source,
            user_managed_networking=self._config.user_managed_networking,
            high_availability_mode=self._config.high_availability_mode,
            disk_encryption=disk_encryption,
            tags=self._config.cluster_tags or None,
            cpu_architecture=(
                consts.CPUArchitecture.MULTI
                if self._config.openshift_version.endswith(f"{consts.CPUArchitecture.MULTI}")
                else self._config.cpu_architecture
            ),
            **extra_vars,
        )

        self._config.cluster_id = cluster.id
        return cluster.id

    def get_olm_operators(self) -> List:
        olm_operators = []
        for operator_name in self._config.olm_operators:
            operator_properties = consts.get_operator_properties(
                operator_name,
                api_ip=self._config.metallb_api_ip,
                ingress_ip=self._config.metallb_ingress_ip,
            )
            operator = {"name": operator_name}
            if operator_properties:
                operator["properties"] = operator_properties
            olm_operators.append(operator)

        return olm_operators

    @property
    def is_sno(self):
        return self.nodes.nodes_count == 1

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

    def get_node_labels(self):
        return {h["id"]: json.loads(h["node_labels"]) for h in self.get_hosts()}

    def get_operators(self):
        return self.api_client.get_cluster_operators(self.id)

    def get_preflight_requirements(self):
        return self.api_client.get_preflight_requirements(self.id)

    def update_infra_env_proxy(self, proxy: models.Proxy) -> None:
        self._infra_env_config.proxy = proxy
        self._infra_env.update_proxy(proxy=proxy)

    def update_tags(self, tags: str):
        log.info(f"Setting cluster tags: {tags} for cluster: {self.id}")
        self.update_config(cluster_tags=tags)
        self.api_client.update_cluster(self.id, {"tags": tags})

    def get_tags(self) -> str:
        tags = self.get_details().tags
        self._config.cluster_tags = tags
        return tags

    def wait_until_hosts_are_disconnected(self, nodes_count: int = None):
        statuses = [consts.NodesStatus.DISCONNECTED]
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count or self.nodes.nodes_count,
            statuses=statuses,
            timeout=consts.DISCONNECTED_TIMEOUT,
        )

    def wait_until_hosts_use_agent_image(self, image: str) -> None:
        wait_till_all_hosts_use_agent_image(
            client=self.api_client,
            cluster_id=self.id,
            image=image,
        )

    @JunitTestCase()
    def wait_until_hosts_are_insufficient(self, nodes_count: int = None):
        statuses = [consts.NodesStatus.INSUFFICIENT]
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            nodes_count=nodes_count or self.nodes.nodes_count,
            statuses=statuses,
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

    def set_disk_encryption(self, mode: str, roles: str, tang_servers: str = None):
        """
        :param mode: encryption mode (e.g. "tpmv2")
        :param roles: To which role to apply
        :param tang_servers: List of tang servers and their thumbprints, e.g:
            [{\"url\":\"http://10.46.46.11:7500\",\"thumbprint\":\"GzLKmSCjScL23gy7rfzLzkH-Mlg\"},
            {\"url\":\"http://10.46.46.62:7500\",\"thumbprint\":\"wenz_yQJ7eAyHJyluAl_JmJmd5E\"}]
        :return: None
        """
        disk_encryption_params = models.DiskEncryption(enable_on=roles, mode=mode, tang_servers=tang_servers)
        self.api_client.update_cluster(self.id, {"disk_encryption": disk_encryption_params})

    def set_ignored_validations(
        self,
        host_validation_ids: list[str] = None,
        cluster_validation_ids: list[str] = None,
        **kwargs,
    ):
        ignore_obj = models.IgnoredValidations(
            host_validation_ids=json.dumps(host_validation_ids) if host_validation_ids else None,
            cluster_validation_ids=json.dumps(cluster_validation_ids) if cluster_validation_ids else None,
        )
        self.api_client.client.v2_set_ignored_validations(self.id, ignore_obj, **kwargs)

    def get_ignored_validations(self, **kwargs) -> models.IgnoredValidations:
        return self.api_client.client.v2_get_ignored_validations(self.id, **kwargs)

    def set_odf(self, properties: str = None, update: bool = False):
        self.set_olm_operator(consts.OperatorType.ODF, properties=properties, update=update)

    def set_cnv(self, properties: str = None, update: bool = False):
        self.set_olm_operator(consts.OperatorType.CNV, properties=properties, update=update)

    def set_lvm(self, properties: str = None, update: bool = False):
        self.set_olm_operator(consts.OperatorType.LVM, properties=properties, update=update)

    def set_mce(self, properties: str = None, update: bool = False):
        self.set_olm_operator(consts.OperatorType.MCE, properties=properties, update=update)

    def set_metallb(self, properties: str = None, update: bool = False):
        if properties is None:
            properties = consts.get_operator_properties(
                consts.OperatorType.METALLB,
                api_vip=self._config.api_vips[0].ip,
                ingress_vip=self._config.ingress_vips[0].ip,
            )

        self.set_olm_operator(consts.OperatorType.METALLB, properties=properties, update=update)

    def unset_odf(self):
        self.unset_olm_operator(consts.OperatorType.ODF)

    def unset_cnv(self):
        self.unset_olm_operator(consts.OperatorType.CNV)

    def unset_lvm(self):
        self.unset_olm_operator(consts.OperatorType.LVM)

    def unset_mce(self):
        self.unset_olm_operator(consts.OperatorType.MCE)

    def unset_metallb(self):
        self.unset_olm_operator(consts.OperatorType.METALLB)

    def unset_olm_operator(self, operator_name):
        log.info(f"Unsetting {operator_name} for cluster: {self.id}")
        cluster = self.api_client.cluster_get(self.id)

        olm_operators = []
        for operator in cluster.monitored_operators:
            if operator.name == operator_name or operator.operator_type == OperatorType.BUILTIN:
                continue
            olm_operators.append({"name": operator.name, "properties": operator.properties})

        self.api_client.update_cluster(self.id, {"olm_operators": olm_operators})

    def set_olm_operator(self, operator_name, properties=None, update=False):
        log.info(f"Setting {operator_name} for cluster: {self.id}")
        cluster = self.api_client.cluster_get(self.id)

        if not update and operator_name in [o.name for o in cluster.monitored_operators]:
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
                master=num_masters or self.nodes.masters_count,
                worker=num_workers or self.nodes.workers_count,
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

        if self._config.platform in [consts.Platforms.NONE, consts.Platforms.EXTERNAL]:
            log.info("On None/External platforms, leaving network management to the user")
            api_vips = ingress_vips = machine_networks = None

        elif self._config.vip_dhcp_allocation or self._high_availability_mode == consts.HighAvailabilityMode.NONE:
            log.info("Letting access VIPs be deducted from machine networks")
            api_vips = ingress_vips = None
            machine_networks = [self.get_machine_networks()[0]]

        elif self._config.load_balancer_type == consts.LoadBalancerType.USER_MANAGED.value:
            log.info("User managed load balancer. Setting the VIPs to the load balancer IP")
            api_vips = ingress_vips = [ApiVip(ip=self._get_load_balancer_ip()).to_dict()]
            machine_networks = None

        else:
            log.info("Assigning VIPs statically")
            access_vips = controller.get_ingress_and_api_vips()
            api_vips = access_vips["api_vips"] if access_vips else None
            ingress_vips = access_vips["ingress_vips"] if access_vips else None
            machine_networks = None

        if self._config.is_ipv4 and self._config.is_ipv6:
            machine_networks = controller.get_all_machine_addresses()

        self.set_advanced_networking(
            vip_dhcp_allocation=self._config.vip_dhcp_allocation,
            cluster_networks=self._config.cluster_networks,
            service_networks=self._config.service_networks,
            machine_networks=machine_networks,
            api_vips=api_vips,
            ingress_vips=ingress_vips,
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

    def get_machine_networks(self) -> List[str]:
        networks = []

        primary_machine_cidr = self.nodes.controller.get_primary_machine_cidr()
        if primary_machine_cidr:
            networks.append(primary_machine_cidr)

        secondary_machine_cidr = self.nodes.controller.get_provisioning_cidr()
        if secondary_machine_cidr:
            networks.append(secondary_machine_cidr)

        if not networks:
            # Support controllers which the machine cidr is not configurable. taking it from the AI instead
            networks = list(self.get_cluster_matching_cidrs(Cluster.get_cluster_hosts(self.get_details())))

            if not networks:
                raise RuntimeError("No matching cidr for DHCP")

        return networks

    def set_network_type(self, network_type: str):
        log.info(f"Setting Network type:{network_type} for cluster: {self.id}")
        self.api_client.update_cluster(self.id, {"network_type": network_type})

    def set_ssh_key(self, ssh_key: str):
        log.info(f"Setting SSH key:{ssh_key} for cluster: {self.id}")
        self.update_config(ssh_public_key=ssh_key)
        self.api_client.update_cluster(self.id, {"ssh_public_key": ssh_key})

    def set_base_dns_domain(self, base_dns_domain: str):
        log.info(f"Setting base DNS domain:{base_dns_domain} for cluster: {self.id}")
        self.update_config(base_dns_domain=base_dns_domain)
        self.api_client.update_cluster(self.id, {"base_dns_domain": base_dns_domain})

    def set_ingress_and_api_vips(self, api_vip: str, ingress_vip: str):
        log.info(f"Setting API VIP address:{api_vip} and ingress VIP address:{ingress_vip} for cluster: {self.id}")
        vips = {
            "api_vips": [{"ip": f"{api_vip}"}],
            "ingress_vips": [{"ip": f"{ingress_vip}"}],
        }
        self.api_client.update_cluster(self.id, vips)

    def set_advanced_networking(
        self,
        vip_dhcp_allocation: Optional[bool] = None,
        cluster_networks: Optional[List[models.ClusterNetwork]] = None,
        service_networks: Optional[List[models.ServiceNetwork]] = None,
        machine_networks: Optional[List[models.MachineNetwork]] = None,
        api_vips: Optional[List[models.ApiVip]] = None,
        ingress_vips: Optional[List[models.IngressVip]] = None,
    ):
        if machine_networks is None:
            machine_networks = self._config.machine_networks
        else:
            machine_networks = [models.MachineNetwork(cidr=cidr) for cidr in machine_networks]

        extra_vars = {}
        if vip_dhcp_allocation is None:
            extra_vars["vip_dhcp_allocation"] = self._config.vip_dhcp_allocation or False
        else:
            extra_vars["vip_dhcp_allocation"] = vip_dhcp_allocation

        advanced_networking = {
            "cluster_networks": cluster_networks if cluster_networks is not None else self._config.cluster_networks,
            "service_networks": service_networks if service_networks is not None else self._config.service_networks,
            "machine_networks": machine_networks,
            "api_vips": api_vips if api_vips is not None else self._config.api_vips,
            "ingress_vips": ingress_vips if ingress_vips is not None else self._config.ingress_vips,
            **extra_vars,
        }

        log.info(f"Updating advanced networking with {advanced_networking} for cluster: {self.id}")

        self.update_config(**advanced_networking)
        self.api_client.update_cluster(self.id, advanced_networking)

    def set_cluster_network_cidr(self, cidr: str, host_prefix: int):
        """
        :param cidr: cluster network cidr (e.g 192.128.0.0/13)
        :param host_prefix: The subnet prefix length to assign to each individual node (e.g 23)
        :return: None
        """
        cluster_network = models.ClusterNetwork(cidr=cidr, host_prefix=host_prefix)
        self.api_client.update_cluster(self.id, {"cluster_networks": [cluster_network]})

    def set_host_name(self, host_id, requested_name):
        log.info(f"Setting Required Host Name:{requested_name}, for Host ID: {host_id}")
        self._infra_env.update_host(host_id=host_id, host_name=requested_name)

    def set_node_labels(self, host_id: str, node_labels: List[dict]):
        log.info(f"Setting required node labels: {node_labels}, for host id: {host_id}")
        self._infra_env.update_host(host_id=host_id, node_labels=node_labels)

    def set_additional_ntp_source(self, ntp_source: List[str]):
        log.info(f"Setting Additional NTP source:{ntp_source}")
        if isinstance(ntp_source, List):
            ntp_source_string = ",".join(ntp_source)
        elif isinstance(ntp_source, str):
            ntp_source_string = ntp_source
        else:
            raise TypeError(
                f"ntp_source must be a string or a list of strings, got: {ntp_source}, type: {type(ntp_source)}"
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

        utils.waiting.wait_till_cluster_is_in_status(
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
            stages=[
                consts.HostsProgressStages.WRITE_IMAGE_TO_DISK,
                consts.HostsProgressStages.REBOOTING,
            ],
            nodes_count=nodes_count,
        )

    def wait_for_host_status(
        self,
        statuses,
        fall_on_error_status=True,
        nodes_count: int = MINIMUM_NODES_TO_WAIT,
        fall_on_pending_status=False,
    ):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=statuses,
            nodes_count=nodes_count,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
        )

    def wait_for_specific_host_status(
        self,
        host,
        statuses,
        status_info="",
        nodes_count: int = MINIMUM_NODES_TO_WAIT,
        timeout: int = consts.NODES_REGISTERED_TIMEOUT,
    ):
        utils.waiting.wait_till_specific_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            host_name=host.get("requested_hostname"),
            statuses=statuses,
            status_info=status_info,
            nodes_count=nodes_count,
            timeout=timeout,
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
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.ERROR],
            timeout=consts.ERROR_TIMEOUT,
        )

    def wait_for_pending_for_input_status(self):
        utils.waiting.wait_till_cluster_is_in_status(
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

    def wait_for_hosts_stage(self, stage: str, inclusive: bool = True, **kwargs):
        index = consts.all_host_stages.index(stage)
        utils.waiting.wait_till_at_least_one_host_is_in_stage(
            client=self.api_client,
            cluster_id=self.id,
            stages=consts.all_host_stages[index:] if inclusive else consts.all_host_stages[index + 1 :],
            nodes_count=self.nodes.nodes_count,
            **kwargs,
        )

    @JunitTestCase()
    def start_install_and_wait_for_installed(
        self,
        wait_for_hosts=True,
        wait_for_operators=True,
        wait_for_cluster_install=True,
        download_kubeconfig=True,
        fall_on_pending_status=False,
    ):
        self.start_install()
        if wait_for_hosts:
            self.wait_for_hosts_to_install(fall_on_pending_status=fall_on_pending_status)
        if wait_for_operators:
            self.wait_for_operators_to_finish()
        if wait_for_cluster_install:
            self.wait_for_install()
        if download_kubeconfig:
            self.download_kubeconfig()

        log.info(f"{self.get_details()}")
        self._is_installed = True

    @JunitTestCase()
    def start_install_s390x_and_wait_for_installed(
        self,
        wait_for_hosts=True,
        wait_for_operators=True,
        wait_for_cluster_install=True,
        download_kubeconfig=True,
        fall_on_pending_status=False,
    ):
        """
        self.api_client.create_cluster(cluster_id=self.id)
        """
        log.info("Start install on s390x and wait for be installed...")

        log.info(f"Not implemented yet ... {self.get_details()}")
        self._is_installed = True

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

    def get_bootstrap_hostname(self):
        hosts = self.get_hosts_by_role(consts.NodeRoles.MASTER)
        for host in hosts:
            if host.get("bootstrap"):
                log.info("Bootstrap node is: %s", host["requested_hostname"])
                return host["requested_hostname"]

    def get_hosts_by_role(self, role, hosts=None):
        return self.api_client.get_hosts_by_role(self.id, role, hosts)

    def get_random_host_by_role(self, role):
        return random.choice(self.get_hosts_by_role(role))

    def get_reboot_required_hosts(self):
        return self.api_client.get_hosts_in_statuses(
            cluster_id=self.id,
            statuses=[consts.NodesStatus.RESETING_PENDING_USER_ACTION],
        )

    def reboot_required_nodes_into_iso_after_reset(self):
        hosts_to_reboot = self.get_reboot_required_hosts()
        self.nodes.run_for_given_nodes_by_cluster_hosts(cluster_hosts=hosts_to_reboot, func_name="reset")

    def wait_for_one_host_to_be_in_wrong_boot_order(self, fall_on_error_status=True, fall_on_pending_status=False):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            status_info=consts.HostStatusInfo.WRONG_BOOT_ORDER,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_at_least_one_host_to_be_in_reboot_timeout(
        self, fall_on_error_status=True, nodes_count=1, fall_on_pending_status=False
    ):
        utils.waiting.wait_till_at_least_one_host_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            status_info=(
                consts.HostStatusInfo.REBOOT_TIMEOUT,
                consts.HostStatusInfo.OLD_REBOOT_TIMEOUT,
            ),
            nodes_count=nodes_count,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_hosts_to_be_in_wrong_boot_order(
        self,
        nodes_count,
        timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        fall_on_error_status=True,
        fall_on_pending_status=False,
    ):
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.NodesStatus.INSTALLING_PENDING_USER_ACTION],
            status_info=consts.HostStatusInfo.WRONG_BOOT_ORDER,
            nodes_count=nodes_count,
            timeout=timeout,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
        )

    def wait_for_ready_to_install(self):
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY],
            timeout=consts.READY_TIMEOUT,
        )
        # This code added due to BZ:1909997, temporarily checking if help to prevent unexpected failure
        time.sleep(10)
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.READY],
            timeout=consts.READY_TIMEOUT,
        )

    def is_in_cancelled_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.CANCELLED],
        )

    def is_in_error(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.ERROR],
        )

    def is_finalizing(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.FINALIZING],
        )

    def is_installing(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING],
        )

    def reset_install(self):
        self.api_client.reset_cluster_install(cluster_id=self.id)

    def is_in_insufficient_status(self):
        return utils.is_cluster_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSUFFICIENT],
        )

    def wait_for_hosts_to_install(
        self,
        timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
        fall_on_error_status=True,
        nodes_count: int = None,
        fall_on_pending_status: bool = False,
    ):
        wait_till_all_hosts_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            nodes_count=nodes_count or self.nodes.nodes_count,
            timeout=timeout,
            fall_on_error_status=fall_on_error_status,
            fall_on_pending_status=fall_on_pending_status,
        )

    def wait_for_operators_to_finish(self, timeout=consts.CLUSTER_INSTALLATION_TIMEOUT, fall_on_error_status=True):
        operators = self.get_operators()

        if fall_on_error_status:
            statuses = [consts.OperatorStatus.AVAILABLE]
        else:
            statuses = [consts.OperatorStatus.AVAILABLE, consts.OperatorStatus.FAILED]

        log.info("Starting to wait for builtin operators")
        operators_utils.wait_till_all_operators_are_in_status(
            client=self.api_client,
            cluster_id=self.id,
            operators_count=len(operators_utils.filter_operators_by_type(operators, OperatorType.BUILTIN)),
            operator_types=[OperatorType.BUILTIN],
            statuses=statuses,
            timeout=timeout,
            fall_on_error_status=False,
        )
        log.info("Starting to wait for OLM operators")
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
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLED],
            timeout=timeout,
        )

    def _ha_not_none_not_external(self):
        return self._high_availability_mode != consts.HighAvailabilityMode.NONE and self._config.platform not in [
            consts.Platforms.NONE,
            consts.Platforms.EXTERNAL,
        ]

    def prepare_nodes(self, is_static_ip: bool = False, **kwargs):
        super(Cluster, self).prepare_nodes(is_static_ip=self._infra_env_config.is_static_ip, **kwargs)
        platform = self.get_details().platform
        assert platform.type in self.api_client.get_cluster_supported_platforms(self.id) or (
            platform.type == consts.Platforms.EXTERNAL
            and platform.external.platform_name == consts.ExternalPlatformNames.OCI
        )  # required to test against stage/production  # Patch for SNO OCI - currently not supported in the service
        self.set_hostnames_and_roles()
        if self._high_availability_mode != consts.HighAvailabilityMode.NONE:
            self.set_host_roles(len(self.nodes.get_masters()), len(self.nodes.get_workers()))

        self.set_installer_args()
        self.validate_static_ip()

    @JunitTestCase()
    def create_custom_manifests(self):
        log.info(f"Adding {len(self._config.custom_manifests)} custom manifests")
        for local_manifest in self._config.custom_manifests:
            with open(local_manifest.local_path, "rb") as f:
                encoded_content = base64.b64encode(f.read()).decode("utf-8", "ignore")

            manifest = self.create_custom_manifest(local_manifest.folder, local_manifest.file_name, encoded_content)

            assert manifest.file_name == local_manifest.file_name
            assert manifest.folder == local_manifest.folder
            log.info(f"Manifest {local_manifest.file_name} was created successfully")

    def validate_params(self):
        for manifest in self._config.custom_manifests:
            assert manifest.local_path.exists(), f"Manifest file does not exist: {manifest.file_name}"
            assert (
                manifest.is_folder_allowed()
            ), f"Invalid value for `folder` {manifest.folder} must be one of {manifest.get_allowed_folders()}"

    def create_custom_manifest(self, folder: str = None, filename: str = None, base64_content: str = None):
        return self.api_client.create_custom_manifest(self.id, folder, filename, base64_content)

    def list_custom_manifests(self) -> models.ListManifests:
        return self.api_client.list_custom_manifests(self.id)

    def delete_custom_manifest(self, filename: str = None, folder: str = None) -> None:
        self.api_client.delete_custom_manifest(self.id, filename, folder)

    @JunitTestCase()
    def prepare_for_installation(self, **kwargs):
        self.create_custom_manifests()
        super().prepare_for_installation(**kwargs)
        self.create_custom_manifests()

    @JunitTestCase()
    def prepare_for_installation_s390x(self, **kwargs):
        log.info("Prepare for installation on s390x")
        self.create_custom_manifests()

    def prepare_networking(self):
        self.nodes.wait_for_networking()
        self.set_network_params(controller=self.nodes.controller)

        # in case of None / External platform / User Managed LB, we need to specify dns records before hosts are ready
        if (
            self.nodes.controller.tf_platform
            in [
                consts.Platforms.NONE,
                consts.Platforms.EXTERNAL,
            ]
            or self._config.load_balancer_type == consts.LoadBalancerType.USER_MANAGED.value
        ):
            self._configure_load_balancer()
            self.nodes.controller.set_dns_for_user_managed_network()
        elif self._high_availability_mode == consts.HighAvailabilityMode.NONE:
            main_cidr = self.get_primary_machine_cidr()
            ip = Cluster.get_ip_for_single_node(self.api_client, self.id, main_cidr)
            self.nodes.controller.set_single_node_ip(ip)
            self.nodes.controller.set_dns(api_ip=ip, ingress_ip=ip)

        self.wait_for_ready_to_install()

        # in case of regular cluster, need to set dns after vips exits
        # in our case when nodes are ready, vips will be there for sure
        if self._ha_not_none_not_external():
            vips_info = self.api_client.get_vips_from_cluster(self.id)
            api_ip = vips_info["api_vips"][0].ip if len(vips_info["api_vips"]) > 0 else ""
            ingress_ip = vips_info["ingress_vips"][0].ip if len(vips_info["ingress_vips"]) > 0 else ""
            self.nodes.controller.set_dns(api_ip=api_ip, ingress_ip=ingress_ip)

    def download_kubeconfig_no_ingress(self, kubeconfig_path: str = None):
        self.api_client.download_kubeconfig_no_ingress(self.id, kubeconfig_path or self._config.kubeconfig_path)

    def download_kubeconfig(self, kubeconfig_path: str = None):
        self.api_client.download_kubeconfig(self.id, kubeconfig_path or self._config.kubeconfig_path)

    def download_installation_logs(self, cluster_tar_path):
        self.api_client.download_cluster_logs(self.id, cluster_tar_path)

    def get_install_config(self):
        return yaml.safe_load(self.api_client.get_cluster_install_config(self.id))

    def update_install_config(self, install_config_params: dict, **kwargs) -> None:
        self.api_client.update_cluster_install_config(self.id, install_config_params, **kwargs)

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
            output=output,
        )

    def host_update_install_progress(self, host_id, current_stage, progress_info=None):
        self.api_client.host_update_progress(self.id, host_id, current_stage, progress_info=progress_info)

    def host_complete_install(self):
        self.api_client.complete_cluster_installation(cluster_id=self.id, is_success=True)

    def wait_for_cluster_validation(
        self,
        validation_section,
        validation_id,
        statuses,
        timeout=consts.VALIDATION_TIMEOUT,
        interval=2,
    ):
        log.info(
            "Wait until cluster %s validation %s is in status %s",
            self.id,
            validation_id,
            statuses,
        )
        try:
            waiting.wait(
                lambda: self.is_cluster_validation_in_status(
                    validation_section=validation_section,
                    validation_id=validation_id,
                    statuses=statuses,
                ),
                timeout_seconds=timeout,
                sleep_seconds=interval,
                waiting_for=f"Cluster validation to be in status {statuses}",
            )
        except BaseException:
            log.error(
                "Cluster validation status is: %s",
                utils.get_cluster_validation_value(
                    self.api_client.cluster_get(self.id),
                    validation_section,
                    validation_id,
                ),
            )
            raise

    def is_cluster_validation_in_status(self, validation_section, validation_id, statuses):
        log.info("Is cluster %s validation %s in status %s", self.id, validation_id, statuses)
        try:
            return (
                utils.get_cluster_validation_value(
                    self.api_client.cluster_get(self.id),
                    validation_section,
                    validation_id,
                )
                in statuses
            )
        except BaseException:
            log.exception("Failed to get cluster %s validation info", self.id)

    def wait_for_host_validation(
        self,
        host_id,
        validation_section,
        validation_id,
        statuses,
        timeout=consts.VALIDATION_TIMEOUT,
        interval=2,
    ):
        log.info(
            "Wait until host %s validation %s is in status %s",
            host_id,
            validation_id,
            statuses,
        )
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
                    self.api_client.cluster_get(self.id),
                    host_id,
                    validation_section,
                    validation_id,
                ),
            )
            raise

    def is_host_validation_in_status(self, host_id, validation_section, validation_id, statuses):
        log.info("Is host %s validation %s in status %s", host_id, validation_id, statuses)
        try:
            return (
                utils.get_host_validation_value(
                    self.api_client.cluster_get(self.id),
                    host_id,
                    validation_section,
                    validation_id,
                )
                in statuses
            )
        except BaseException:
            log.exception("Failed to get cluster %s validation info", self.id)

    def wait_for_cluster_to_be_in_installing_pending_user_action_status(self):
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING_PENDING_USER_ACTION],
            timeout=consts.PENDING_USER_ACTION_TIMEOUT,
        )

    def wait_for_cluster_to_be_in_installing_status(self):
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.INSTALLING],
            timeout=consts.START_CLUSTER_INSTALLATION_TIMEOUT,
        )

    def wait_for_cluster_to_be_in_finalizing_status(self):
        utils.waiting.wait_till_cluster_is_in_status(
            client=self.api_client,
            cluster_id=self.id,
            statuses=[consts.ClusterStatus.FINALIZING, consts.ClusterStatus.INSTALLED],
            timeout=consts.CLUSTER_INSTALLATION_TIMEOUT,
            break_statuses=[consts.ClusterStatus.ERROR],
        )

    def wait_for_cluster_to_be_in_status(self, statuses, timeout=consts.ERROR_TIMEOUT):
        utils.waiting.wait_till_cluster_is_in_status(
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

    def _configure_load_balancer(self):
        main_cidr = self.get_primary_machine_cidr()
        secondary_cidr = self.nodes.controller.get_provisioning_cidr()

        master_ips = self.get_master_ips(self.id, main_cidr) + self.get_master_ips(self.id, secondary_cidr)
        worker_ips = self.get_worker_ips(self.id, main_cidr)

        load_balancer_ip = self._get_load_balancer_ip()

        tf = terraform_utils.TerraformUtils(working_dir=self.nodes.controller.tf_folder)
        lb_controller = LoadBalancerController(tf)
        lb_controller.set_load_balancing_config(load_balancer_ip, master_ips, worker_ips)

    def _get_load_balancer_ip(self) -> str:
        main_cidr = self.get_primary_machine_cidr()
        return str(IPNetwork(main_cidr).ip + 1)

    @classmethod
    def _get_namespace_index(cls, libvirt_network_if):
        # Hack to retrieve namespace index - does not exist in tests
        matcher = re.match(r"^tt(\d+)$", libvirt_network_if)
        return int(matcher.groups()[0]) if matcher is not None else 0

    def get_inventory_host_nics_data(self, host: dict, ipv4_first=True):
        return self.api_client.get_inventory_host_nics_data(host, ipv4_first)

    @staticmethod
    def get_cluster_hosts(cluster: models.cluster.Cluster) -> List[ClusterHost]:
        return [ClusterHost(h) for h in cluster.hosts]

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
        interfaces = client.get_inventory_host_nics_data(cluster_info["hosts"][0], ipv4_first=ipv4_first)
        for intf in interfaces:
            ip = intf.get("ip")
            if ip and IPAddress(ip) in network:
                return ip
        raise Exception("IP for single node not found")

    def get_master_ips(self, cluster_id: str, network: str):
        return self.api_client.get_ips_for_role(cluster_id, network, consts.NodeRoles.MASTER)

    def get_worker_ips(self, cluster_id: str, network: str):
        return self.api_client.get_ips_for_role(cluster_id, network, consts.NodeRoles.WORKER)

    def get_host_disks(self, host, filter=None):
        hosts = self.get_hosts()
        selected_host = [h for h in hosts if h["id"] == host["id"]]
        disks = json.loads(selected_host[0]["inventory"])["disks"]
        if not filter:
            return [disk for disk in disks]
        else:
            return [disk for disk in disks if filter(disk)]

    def wait_and_kill_installer(self, host):
        # Wait for specific host to be in installing in progress
        self.wait_for_specific_host_status(host=host, statuses=[consts.NodesStatus.INSTALLING_IN_PROGRESS])
        # Kill installer to simulate host error
        selected_node = self.nodes.get_node_from_cluster_host(host)
        selected_node.kill_installer()

    @staticmethod
    def format_host_current_network(hosts_list: List) -> dict[str, dict[str, List[str]]]:
        """
        return:
        host_network["mac_address"] = {
            ipv4_addresseses = []
            ipv4_addresseses = []
        }
        """
        log.debug(f"hosts list is: {hosts_list}")
        host_network = {}
        for host in hosts_list:
            log.debug(f"mapping host network for host: {host['requested_hostname']}")
            inventory = yaml.safe_load(host["inventory"])

            interfaces = inventory["interfaces"]
            for interface in interfaces:
                for _, address_version in consts.IP_VERSIONS.items():
                    if address_version in interface.keys():
                        if len(interface[address_version]) != 0:
                            host_network[interface["mac_address"]] = {address_version: interface[address_version]}
        log.debug(f"host_network {host_network}")
        return host_network

    @staticmethod
    def format_host_from_config_mapping_file(config: str) -> dict[str, dict[str, List[str]]]:
        """
        return:
        host_network["mac_address"] = {
            ipv4_addresseses : [],
            ipv4_addresseses : []
        }
        """
        host_network = {}

        _config = yaml.safe_load(config)

        for host in _config:
            for expected_host_interfaces in host["mac_interface_map"]:
                expected_interface_name, expected_interface_mac = (
                    expected_host_interfaces["logical_nic_name"],
                    expected_host_interfaces["mac_address"],
                )

                network_yaml = yaml.safe_load(unescape_string(host["network_yaml"]))
                for current_interface in network_yaml["interfaces"]:
                    if (
                        current_interface["name"] == expected_interface_name
                        or "bond" in str(current_interface["name"]).lower()
                    ):
                        for address_version in consts.IP_VERSIONS.keys():
                            if address_version not in current_interface.keys():
                                continue
                            address = current_interface[address_version]["address"]
                            if len(address) == 0:
                                continue
                            host_network[expected_interface_mac] = {
                                consts.IP_VERSIONS[address_version]: [
                                    f'{item["ip"]}/{item["prefix-length"]}' for item in address
                                ]
                            }

        return host_network

    def validate_static_ip(self) -> None:
        if self._infra_env_config.static_network_config is None:
            log.debug("Skipping static IP validation")
            return

        log.info("Starting static IP validation")
        self.wait_until_hosts_are_discovered()

        current_host_network = self.format_host_current_network(
            hosts_list=self.api_client.get_cluster_hosts(cluster_id=self._config.cluster_id)
        )
        if current_host_network == {}:
            raise Exception("Couldn't get current host network")

        config_host_network = self.format_host_from_config_mapping_file(
            config=str(self._infra_env_config.static_network_config)
        )

        if config_host_network == {}:
            raise Exception("Couldn't find host network configurations")

        host_failure = []

        for mac_address in config_host_network.keys():
            if mac_address not in current_host_network.keys() and not self._infra_env_config.is_bonded:
                host_failure.append(f"missing mac address {mac_address}")
                continue
            for _, version in consts.IP_VERSIONS.items():
                if version not in config_host_network:
                    continue
                config_address = config_host_network[mac_address][version]
                if len(config_address) > 0:
                    for addr in config_address:
                        if addr not in config_host_network[mac_address][version]:
                            host_failure.append(f"missing IP address {addr}")

        log.info(f"Static IP validation: host network {current_host_network}")
        log.info(f"Static IP validation:expected address {config_host_network} ")

        if host_failure:
            raise AssertionError(host_failure)

        del host_failure, config_host_network, current_host_network
        log.info("Static IP validation passed")
