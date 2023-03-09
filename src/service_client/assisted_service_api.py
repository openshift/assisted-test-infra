# -*- coding: utf-8 -*-
import base64
import contextlib
import ipaddress
import json
import os
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import requests
import waiting
from assisted_service_client import ApiClient, Configuration, api, models
from junit_report import CaseFormatKeys, JsonJunitExporter
from netaddr import IPAddress, IPNetwork
from retry import retry

import consts
from service_client.logger import log


class InventoryClient(object):
    def __init__(self, inventory_url: str, offline_token: Optional[str], pull_secret: str):
        self.inventory_url = inventory_url
        configs = Configuration()
        configs.host = self.get_host(configs)
        configs.verify_ssl = False
        self.set_config_auth(configs, offline_token)
        self._set_x_secret_key(configs, pull_secret)

        self.api = ApiClient(configuration=configs)
        self.client = api.InstallerApi(api_client=self.api)
        self.events = api.EventsApi(api_client=self.api)
        self.versions = api.VersionsApi(api_client=self.api)
        self.domains = api.ManagedDomainsApi(api_client=self.api)
        self.operators = api.OperatorsApi(api_client=self.api)
        self.manifest = api.ManifestsApi(api_client=self.api)

        fmt = CaseFormatKeys(
            case_name="cluster-event-test", static_case_name=True, severity_key="severity", case_timestamp="event_time"
        )
        self._events_junit_exporter = JsonJunitExporter(fmt)

    def get_host(self, configs: Configuration) -> str:
        parsed_host = urlparse(configs.host)
        parsed_inventory_url = urlparse(self.inventory_url)
        return parsed_host._replace(netloc=parsed_inventory_url.netloc, scheme=parsed_inventory_url.scheme).geturl()

    @classmethod
    def set_config_auth(cls, c: Configuration, offline_token: Optional[str]) -> None:
        if not offline_token:
            log.info("OFFLINE_TOKEN not set, skipping authentication headers")
            return

        @retry(exceptions=requests.HTTPError, tries=5, delay=5)
        def refresh_api_key(config: Configuration) -> None:
            # Get the properly padded key segment
            auth = config.api_key.get("Authorization", None)
            if auth is not None:
                segment = auth.split(".")[1]
                padding = len(segment) % 4
                segment = segment + padding * "="

                expires_on = json.loads(base64.b64decode(segment))["exp"]

                # if this key doesn't expire or if it has more than 10 minutes left, don't refresh
                remaining = expires_on - time.time()
                if expires_on == 0 or remaining > 600:
                    return

            # fetch new key if expired or not set yet
            params = {
                "client_id": "cloud-services",
                "grant_type": "refresh_token",
                "refresh_token": offline_token,
            }

            log.info("Refreshing API key")
            response = requests.post(os.environ.get("SSO_URL"), data=params)
            response.raise_for_status()

            config.api_key["Authorization"] = response.json()["access_token"]

        c.api_key_prefix["Authorization"] = "Bearer"
        c.refresh_api_key_hook = refresh_api_key

    @classmethod
    def _set_x_secret_key(cls, c: Configuration, pull_secret: str) -> None:
        if not pull_secret:
            log.info("pull secret not set, skipping agent authentication headers")
            return

        log.info("Setting X-Secret-Key")
        c.api_key["X-Secret-Key"] = json.loads(pull_secret)["auths"]["cloud.openshift.com"]["auth"]

    def wait_for_api_readiness(self, timeout: int) -> None:
        log.info("Waiting for inventory api to be ready")
        waiting.wait(
            lambda: self.clusters_list() is not None,
            timeout_seconds=timeout,
            sleep_seconds=5,
            waiting_for="Wait till inventory is ready",
            expected_exceptions=Exception,
        )

    def create_cluster(
        self, name: str, ssh_public_key: Optional[str] = None, **cluster_params
    ) -> models.cluster.Cluster:
        cluster = models.ClusterCreateParams(name=name, ssh_public_key=ssh_public_key, **cluster_params)
        log.info("Creating cluster with params %s", cluster.__dict__)
        result = self.client.v2_register_cluster(new_cluster_params=cluster)
        return result

    def create_infra_env(
        self, name: str, ssh_public_key: Optional[str] = None, **infra_env_params
    ) -> models.infra_env.InfraEnv:
        infra_env = models.InfraEnvCreateParams(name=name, ssh_authorized_key=ssh_public_key, **infra_env_params)
        log.info("Creating infra-env with params %s", infra_env.__dict__)
        result = self.client.register_infra_env(infraenv_create_params=infra_env)
        return result

    def create_day2_cluster(self, name: str, cluster_uuid: str, **cluster_params) -> models.cluster.Cluster:
        cluster = models.ImportClusterParams(name=name, openshift_cluster_id=cluster_uuid, **cluster_params)
        log.info("Creating day 2 cluster with params %s", cluster.__dict__)
        result = self.client.v2_import_cluster(new_import_cluster_params=cluster)
        return result

    def get_cluster_hosts(self, cluster_id: str) -> List[Dict[str, Any]]:
        cluster_details = self.cluster_get(cluster_id)
        return list(map(lambda host: host.to_dict(), cluster_details.hosts))

    def get_infra_env_hosts(self, infra_env_id: str) -> List[Dict[str, Any]]:
        return self.client.v2_list_hosts(infra_env_id=infra_env_id)

    def get_infra_env(self, infra_env_id: str) -> models.infra_env.InfraEnv:
        return self.client.get_infra_env(infra_env_id=infra_env_id)

    def delete_infra_env(self, infra_env_id: str) -> None:
        log.info("Deleting infra_env %s", infra_env_id)
        self.client.deregister_infra_env(infra_env_id=infra_env_id)

    def get_cluster_operators(self, cluster_id: str) -> List[models.MonitoredOperator]:
        return self.cluster_get(cluster_id=cluster_id).monitored_operators

    def get_hosts_in_statuses(self, cluster_id: str, statuses: List[str]) -> List[dict]:
        hosts = self.get_cluster_hosts(cluster_id)
        return [host for host in hosts if host["status"] in statuses]

    def get_hosts_in_error_status(self, cluster_id: str):
        return self.get_hosts_in_statuses(cluster_id, [consts.NodesStatus.ERROR])

    def clusters_list(self) -> List[Dict[str, Any]]:
        return self.client.v2_list_clusters()

    def infra_envs_list(self) -> List[Dict[str, Any]]:
        return self.client.list_infra_envs()

    def get_all_clusters(self) -> List[Dict[str, Any]]:
        return self.client.v2_list_clusters(get_unregistered_clusters=True)

    def cluster_get(self, cluster_id: str) -> models.cluster.Cluster:
        return self.client.v2_get_cluster(cluster_id=cluster_id, get_unregistered_clusters=True)

    def get_infra_env_by_cluster_id(self, cluster_id: str) -> List[Union[models.infra_env.InfraEnv, Dict[str, Any]]]:
        infra_envs = self.infra_envs_list()
        return [infra_env for infra_env in infra_envs if infra_env["cluster_id"] == cluster_id]

    def update_infra_env(self, infra_env_id: str, infra_env_update_params):
        log.info("Updating infra env %s with values %s", infra_env_id, infra_env_update_params)
        self.client.update_infra_env(infra_env_id=infra_env_id, infra_env_update_params=infra_env_update_params)

    def update_host(
        self,
        infra_env_id: str,
        host_id: str,
        host_role: str = None,
        host_name: str = None,
        node_labels: List[dict] = None,
        disks_skip_formatting: list[dict] = None,
    ):
        host_update_params = models.HostUpdateParams(
            host_role=host_role,
            host_name=host_name,
            node_labels=node_labels,
            disks_skip_formatting=disks_skip_formatting,
        )
        self.client.v2_update_host(infra_env_id=infra_env_id, host_id=host_id, host_update_params=host_update_params)

    def select_installation_disk(self, infra_env_id: str, host_id: str, disk_paths: List[dict]) -> None:
        log.info("Setting installation disk for host %s in infra_env %s", host_id, infra_env_id)

        def role_to_selected_disk_config(disk_id: str, role: models.DiskRole) -> models.DiskConfigParams:
            return models.DiskConfigParams(id=disk_id, role=role)

        disks_selected_config = [
            role_to_selected_disk_config(disk["disk_id"] if "disk_id" in disk else disk["path"], disk["role"])
            for disk in disk_paths
        ]

        params = models.HostUpdateParams(disks_selected_config=disks_selected_config)
        return self.client.v2_update_host(infra_env_id=infra_env_id, host_id=host_id, host_update_params=params)

    def set_pull_secret(self, cluster_id: str, pull_secret: str) -> models.cluster.Cluster:
        log.info("Setting pull secret for cluster %s", cluster_id)
        update_params = models.V2ClusterUpdateParams(pull_secret=pull_secret)
        return self.update_cluster(cluster_id=cluster_id, update_params=update_params)

    def update_cluster(self, cluster_id, update_params) -> models.cluster.Cluster:
        log.info("Updating cluster %s with params %s", cluster_id, update_params)
        return self.client.v2_update_cluster(cluster_id=cluster_id, cluster_update_params=update_params)

    def delete_cluster(self, cluster_id: str):
        log.info("Deleting cluster %s", cluster_id)
        self.client.v2_deregister_cluster(cluster_id=cluster_id)

    def deregister_host(self, infra_env_id: str, host_id: str):
        log.info(f"Deleting host {host_id} in infra_env {infra_env_id}")
        self.client.v2_deregister_host(infra_env_id=infra_env_id, host_id=host_id)

    def get_hosts_id_with_macs(self, cluster_id: str) -> Dict[Any, List[str]]:
        hosts = self.get_cluster_hosts(cluster_id)
        hosts_data = {}
        for host in hosts:
            inventory = json.loads(host.get("inventory", '{"interfaces":[]}'))
            hosts_data[host["id"]] = [interface["mac_address"] for interface in inventory["interfaces"]]
        return hosts_data

    def get_host_by_mac(self, cluster_id: str, mac: str) -> Dict[str, Any]:
        hosts = self.get_cluster_hosts(cluster_id)

        for host in hosts:
            inventory = json.loads(host.get("inventory", '{"interfaces":[]}'))
            if mac.lower() in [interface["mac_address"].lower() for interface in inventory["interfaces"]]:
                return host

    def get_host_by_name(self, cluster_id: str, host_name: str) -> Dict[str, Any]:
        hosts = self.get_cluster_hosts(cluster_id)

        for host in hosts:
            hostname = host.get("requested_hostname")
            if hostname == host_name:
                log.info(f"Requested host by name: {host_name}, host details: {host}")
                return host

    def download_and_save_file(self, cluster_id: str, file_name: str, file_path: str) -> None:
        log.info("Downloading %s to %s", file_name, file_path)
        response = self.client.v2_download_cluster_files(
            cluster_id=cluster_id, file_name=file_name, _preload_content=False
        )
        with open(file_path, "wb") as _file:
            _file.write(response.data)

    def download_and_save_infra_env_file(self, infra_env_id: str, file_name: str, file_path: str) -> None:
        log.info(f"Downloading {file_name} to {file_path}")
        response = self.client.v2_download_infra_env_files(
            infra_env_id=infra_env_id, file_name=file_name, _preload_content=False
        )
        with open(file_path, "wb") as _file:
            _file.write(response.data)

    def download_manifests(self, cluster_id: str, dir_path: str) -> None:
        log.info(f"Downloading manifests for cluster {cluster_id} into {dir_path}")
        response = self.manifest.v2_list_cluster_manifests(cluster_id=cluster_id, _preload_content=False)
        for record in json.loads(response.data):
            response = self.manifest.v2_download_cluster_manifest(
                cluster_id=cluster_id, file_name=record["file_name"], folder=record["folder"], _preload_content=False
            )
            with open(os.path.join(dir_path, record["file_name"]), "wb") as _file:
                _file.write(response.data)

    def download_kubeconfig_no_ingress(self, cluster_id: str, kubeconfig_path: str) -> None:
        log.info("Downloading kubeconfig-noingress to %s", kubeconfig_path)
        response = self.client.v2_download_cluster_credentials(
            cluster_id=cluster_id, file_name="kubeconfig-noingress", _preload_content=False
        )
        with open(kubeconfig_path, "wb") as _file:
            _file.write(response.data)

    def download_host_ignition(self, infra_env_id: str, host_id: str, destination: str) -> None:
        log.info("Downloading host %s infra_env %s ignition files to %s", host_id, infra_env_id, destination)

        response = self.client.v2_download_host_ignition(
            infra_env_id=infra_env_id, host_id=host_id, _preload_content=False
        )
        with open(os.path.join(destination, f"host_{host_id}.ign"), "wb") as _file:
            _file.write(response.data)

    def download_kubeconfig(self, cluster_id: str, kubeconfig_path: str) -> None:
        log.info("Downloading kubeconfig to %s", kubeconfig_path)
        response = self.client.v2_download_cluster_credentials(
            cluster_id=cluster_id, file_name="kubeconfig", _preload_content=False
        )
        with open(kubeconfig_path, "wb") as _file:
            _file.write(response.data)

    def download_metrics(self, dest: str) -> None:
        log.info("Downloading metrics to %s", dest)

        url = self.inventory_url
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"http://{url}"
        response = requests.get(f"{url}/metrics")
        response.raise_for_status()

        with open(dest, "w") as _file:
            _file.write(response.text)

    def install_cluster(self, cluster_id: str) -> models.cluster.Cluster:
        log.info("Installing cluster %s", cluster_id)
        return self.client.v2_install_cluster(cluster_id=cluster_id)

    def install_day2_cluster(self, cluster_id: str) -> models.cluster.Cluster:
        log.info("Installing day2 cluster %s", cluster_id)
        return self.client.install_hosts(cluster_id=cluster_id)

    def install_day2_host(self, infra_env_id: str, host_id: str) -> models.cluster.Cluster:
        log.info("Installing day2 host %s, infra_env_id %s", host_id, infra_env_id)
        return self.client.v2_install_host(infra_env_id=infra_env_id, host_id=host_id)

    def download_cluster_logs(self, cluster_id: str, output_file: str) -> None:
        log.info("Downloading cluster logs to %s", output_file)
        response = self.client.v2_download_cluster_logs(cluster_id=cluster_id, _preload_content=False)
        with open(output_file, "wb") as _file:
            _file.write(response.data)

    def get_events(
        self,
        cluster_id: Optional[str] = "",
        host_id: Optional[str] = "",
        infra_env_id: Optional[str] = "",
        categories=None,
    ) -> List[Dict[str, str]]:
        if categories is None:
            categories = ["user"]
        # Get users events
        response = self.events.v2_list_events(
            cluster_id=cluster_id,
            host_id=host_id,
            infra_env_id=infra_env_id,
            categories=categories,
            _preload_content=False,
        )

        return json.loads(response.data)

    def download_cluster_events(self, cluster_id: str, output_file: str, categories=None) -> None:
        if categories is None:
            categories = ["user"]
        log.info("Downloading cluster events to %s", output_file)

        with open(output_file, "wb") as _file:
            events = self.get_events(cluster_id, categories=categories)
            _file.write(json.dumps(events, indent=4).encode())
            self._events_junit_exporter.collect(events, suite_name="cluster_events", xml_suffix=cluster_id)

    def download_infraenv_events(self, infra_env_id: str, output_file: str, categories: str = None) -> None:
        if categories is None:
            categories = ["user"]
        log.info("Downloading infraenv events to %s", output_file)

        with open(output_file, "wb") as _file:
            events = self.get_events(infra_env_id=infra_env_id, categories=categories)
            _file.write(json.dumps(events, indent=4).encode())

    def download_host_logs(self, cluster_id: str, host_id: str, output_file) -> None:
        log.info("Downloading host logs to %s", output_file)
        response = self.client.v2_download_cluster_logs(cluster_id=cluster_id, host_id=host_id, _preload_content=False)
        with open(output_file, "wb") as _file:
            _file.write(response.data)

    def cancel_cluster_install(self, cluster_id: str) -> models.cluster.Cluster:
        log.info("Canceling installation of cluster %s", cluster_id)
        return self.client.v2_cancel_installation(cluster_id=cluster_id)

    def reset_cluster_install(self, cluster_id: str) -> models.cluster.Cluster:
        log.info("Reset installation of cluster %s", cluster_id)
        return self.client.v2_reset_cluster(cluster_id=cluster_id)

    def bind_host(self, infra_env_id: str, host_id: str, cluster_id: str) -> None:
        log.info(f"Enabling host: {host_id}, from infra_env {infra_env_id}, in cluster id: {cluster_id}")
        bind_host_params = models.BindHostParams(cluster_id=cluster_id)
        self.client.bind_host(infra_env_id=infra_env_id, host_id=host_id, bind_host_params=bind_host_params)

    def unbind_host(self, infra_env_id: str, host_id: str) -> None:
        log.info(f"Disabling host: {host_id}, from infra_env {infra_env_id}")
        self.client.unbind_host(infra_env_id=infra_env_id, host_id=host_id)

    def set_cluster_proxy(
        self, cluster_id: str, http_proxy: str, https_proxy: Optional[str] = "", no_proxy: Optional[str] = ""
    ) -> models.cluster.Cluster:
        log.info("Setting proxy for cluster %s", cluster_id)
        update_params = models.V2ClusterUpdateParams(http_proxy=http_proxy, https_proxy=https_proxy, no_proxy=no_proxy)
        return self.update_cluster(cluster_id=cluster_id, update_params=update_params)

    def get_cluster_install_config(self, cluster_id: str) -> str:
        log.info("Getting install-config for cluster %s", cluster_id)
        return self.client.v2_get_cluster_install_config(cluster_id=cluster_id)

    def patch_discovery_ignition(self, infra_env_id: str, ignition_info: str) -> None:
        infra_env_update_params = models.InfraEnvUpdateParams(ignition_config_override=json.dumps(ignition_info))
        self.update_infra_env(infra_env_id=infra_env_id, infra_env_update_params=infra_env_update_params)

    def get_discovery_ignition(self, infra_env_id: str) -> str:
        infra_env = self.get_infra_env(infra_env_id=infra_env_id)
        return infra_env.ingition_config_override

    def register_host(self, infra_env_id: str, host_id: str) -> None:
        log.info(f"Registering host: {host_id} to cluster: {infra_env_id}")
        host_params = models.HostCreateParams(host_id=host_id)
        self.client.v2_register_host(infra_env_id=infra_env_id, new_host_params=host_params)

    def host_get_next_step(self, infra_env_id: str, host_id: str) -> models.Steps:
        log.info(f"Getting next step for host: {host_id} in cluster: {infra_env_id}")
        return self.client.v2_get_next_steps(infra_env_id=infra_env_id, host_id=host_id)

    def host_post_step_result(self, infra_env_id: str, host_id: str, **kwargs) -> None:
        reply = models.StepReply(**kwargs)
        self.client.v2_post_step_reply(infra_env_id=infra_env_id, host_id=host_id, reply=reply)

    def host_update_progress(
        self, infra_env_id: str, host_id: str, current_stage: models.HostStage, progress_info=None
    ) -> None:
        host_progress = models.HostProgress(current_stage=current_stage, progress_info=progress_info)
        self.client.v2_update_host_install_progress(
            infra_env_id=infra_env_id, host_id=host_id, host_progress=host_progress
        )

    def complete_cluster_installation(self, cluster_id: str, is_success: bool, error_info=None) -> None:
        completion_params = models.CompletionParams(is_success=is_success, error_info=error_info)
        self.client.v2_complete_installation(cluster_id=cluster_id, completion_params=completion_params)

    def get_cluster_admin_credentials(self, cluster_id: str) -> models.Credentials:
        return self.client.v2_get_credentials(cluster_id=cluster_id)

    def get_versions(self) -> dict:
        response = self.versions.v2_list_component_versions()
        return json.loads(json.dumps(response.to_dict(), sort_keys=True, default=str))

    def get_openshift_versions(self) -> models.OpenshiftVersions:
        return self.versions.v2_list_supported_openshift_versions()

    def get_supported_operators(self) -> List[str]:
        return self.operators.v2_list_supported_operators()

    # TODO remove in favor of get_preflight_requirements
    def get_cluster_host_requirements(self, cluster_id: str) -> models.ClusterHostRequirementsList:
        return self.client.get_cluster_host_requirements(cluster_id=cluster_id)

    def get_managed_domains(self) -> models.ListManagedDomains:
        return self.domains.v2_list_managed_domains()

    def get_preflight_requirements(self, cluster_id: str):
        return self.client.v2_get_preflight_requirements(cluster_id=cluster_id)

    def get_hosts_by_role(self, cluster_id: str, role, hosts=None):
        hosts = hosts or self.get_cluster_hosts(cluster_id)
        nodes_by_role = []
        for host in hosts:
            if host["role"] == role:
                nodes_by_role.append(host)
        log.info(f"Found hosts: {nodes_by_role}, that has the role: {role}")
        return nodes_by_role

    def get_api_vip(self, cluster_info: dict, cluster_id: str = None):
        cluster = cluster_info or self.cluster_get(cluster_id)
        api_vip = cluster.get("api_vip")
        user_managed_networking = cluster.get("user_managed_networking")

        if not api_vip and user_managed_networking:
            log.info("API VIP is not set, searching for api ip on masters")
            hosts = cluster.get("hosts") or cluster.to_dict()["hosts"]
            masters = self.get_hosts_by_role(cluster["id"], consts.NodeRoles.MASTER, hosts=hosts)
            api_vip = self._wait_for_api_vip(masters)

        log.info("api vip is %s", api_vip)
        return api_vip

    @classmethod
    def _wait_for_api_vip(cls, hosts, timeout=180):
        """Enable some grace time for waiting for API's availability."""
        return waiting.wait(
            lambda: cls.get_kube_api_ip(hosts=hosts), timeout_seconds=timeout, sleep_seconds=5, waiting_for="API's IP"
        )

    # needed for None platform and single node
    # we need to get ip where api is running
    @classmethod
    def get_kube_api_ip(cls, hosts):
        for host in hosts:
            for ip in cls.get_inventory_host_ips_data(host):
                if cls.is_kubeapi_service_ready(ip):
                    return ip

    @classmethod
    def get_inventory_host_ips_data(cls, host: dict):
        nics = cls.get_inventory_host_nics_data(host)
        return [nic["ip"] for nic in nics]

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

    @staticmethod
    def get_inventory_host_nics_data(host: dict, ipv4_first=True) -> List[Dict[str, str]]:
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

    def get_hosts_nics_data(self, hosts: List[Union[dict, models.Host]], ipv4_first: bool = True):
        return [self.get_inventory_host_nics_data(h, ipv4_first=ipv4_first) for h in hosts]

    def get_ips_for_role(self, cluster_id, network, role) -> List[str]:
        cluster_info = self.cluster_get(cluster_id).to_dict()
        ret = []
        net = IPNetwork(network)
        hosts_interfaces = self.get_hosts_nics_data([h for h in cluster_info["hosts"] if h["role"] == role])
        for host_interfaces in hosts_interfaces:
            for intf in host_interfaces:
                ip = IPAddress(intf["ip"])
                if ip in net:
                    ret = ret + [intf["ip"]]
        return ret

    def get_vips_from_cluster(self, cluster_id: str) -> Dict[str, str]:
        cluster_info = self.cluster_get(cluster_id)
        return dict(api_vip=cluster_info.api_vip, ingress_vip=cluster_info.ingress_vip)

    def get_cluster_supported_platforms(self, cluster_id: str) -> List[str]:
        return self.client.get_cluster_supported_platforms(cluster_id)
