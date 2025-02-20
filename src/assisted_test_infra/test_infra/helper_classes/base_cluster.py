from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union

from assisted_service_client import models
from junit_report import JunitTestCase

import consts
from assisted_test_infra.test_infra import BaseClusterConfig, BaseInfraEnvConfig, Nodes
from assisted_test_infra.test_infra.controllers.node_controllers import Node
from assisted_test_infra.test_infra.helper_classes.cluster_host import ClusterHost
from assisted_test_infra.test_infra.helper_classes.entity import Entity
from assisted_test_infra.test_infra.helper_classes.infra_env import InfraEnv
from assisted_test_infra.test_infra.utils.waiting import wait_till_all_hosts_are_in_status
from service_client import InventoryClient, log


class BaseCluster(Entity, ABC):
    _config: BaseClusterConfig

    def __init__(
        self,
        api_client: InventoryClient,
        config: BaseClusterConfig,
        infra_env_config: BaseInfraEnvConfig,
        nodes: Optional[Nodes] = None,
    ):
        self._infra_env_config = infra_env_config
        self._infra_env: Optional[InfraEnv] = None

        super().__init__(api_client, config, nodes)

        # Update infraEnv configurations
        self._infra_env_config.cluster_id = config.cluster_id
        self._infra_env_config.openshift_version = self._config.openshift_version
        self._infra_env_config.pull_secret = self._config.pull_secret

    @property
    def id(self) -> str:
        return self._config.cluster_id

    def get_details(self) -> Union[models.infra_env.InfraEnv, models.cluster.Cluster]:
        return self.api_client.cluster_get(self.id)

    def delete(self):
        self.deregister_infraenv()
        if self.id:
            self.api_client.delete_cluster(self.id)
            self._config.cluster_id = None

    def deregister_infraenv(self):
        if self._infra_env:
            self._infra_env.deregister()
        self._infra_env = None

    def cancel_install(self):
        self.api_client.cancel_cluster_install(cluster_id=self.id)

    @abstractmethod
    def start_install_and_wait_for_installed(self, **kwargs):
        pass

    def download_image(self, iso_download_path: str = None, static_network_config=None) -> Path:
        if self._infra_env is None:
            log.warning("No infra_env found. Generating infra_env and downloading ISO")
            return self.generate_and_download_infra_env(
                static_network_config=static_network_config,
                iso_download_path=iso_download_path or self._config.iso_download_path,
                iso_image_type=self._config.iso_image_type,
            )
        return self._infra_env.download_image(iso_download_path or self._config.iso_download_path)

    def download_ipxe_script(self, static_network_config=None) -> Path:
        if self._infra_env is None:
            log.warning("No infra_env found. Generating infra_env and downloading iPXE script file")
            self.generate_infra_env(
                static_network_config=static_network_config,
            )
            self._infra_env.download_infra_env_file("ipxe-script", self._config.install_working_dir)

    @JunitTestCase()
    def generate_and_download_infra_env(
        self,
        iso_download_path=None,
        static_network_config=None,
        iso_image_type=None,
        ssh_key=None,
        ignition_info=None,
        proxy=None,
        cpu_architecture: Optional[str] = None,
    ) -> Path:
        self.generate_infra_env(
            static_network_config=static_network_config,
            iso_image_type=iso_image_type,
            ssh_key=ssh_key,
            ignition_info=ignition_info,
            proxy=proxy,
            cpu_architecture=cpu_architecture,
        )
        return self.download_infra_env_image(iso_download_path=iso_download_path or self._config.iso_download_path)

    def generate_infra_env(
        self,
        static_network_config=None,
        iso_image_type=None,
        ssh_key=None,
        ignition_info=None,
        proxy=None,
        cpu_architecture: Optional[str] = None,
    ) -> InfraEnv:
        if self._infra_env:
            return self._infra_env

        self._infra_env = self.create_infra_env(
            static_network_config, iso_image_type, ssh_key, ignition_info, proxy, cpu_architecture
        )
        return self._infra_env

    def download_infra_env_image(self, iso_download_path=None) -> Path:
        iso_download_path = iso_download_path or self._config.iso_download_path
        log.debug(f"Downloading ISO to {iso_download_path}")
        return self._infra_env.download_image(iso_download_path=iso_download_path)

    def create_infra_env(
        self,
        static_network_config=None,
        iso_image_type=None,
        ssh_key=None,
        ignition_info=None,
        proxy=None,
        cpu_architecture: Optional[str] = None,
    ) -> InfraEnv:
        self._infra_env_config.ssh_public_key = ssh_key or self._config.ssh_public_key
        self._infra_env_config.iso_image_type = iso_image_type or self._config.iso_image_type
        self._infra_env_config.static_network_config = static_network_config
        self._infra_env_config.ignition_config_override = ignition_info
        self._infra_env_config.proxy = proxy or self._config.proxy
        self._infra_env_config.cpu_architecture = cpu_architecture or self._config.cpu_architecture
        infra_env = InfraEnv(api_client=self.api_client, config=self._infra_env_config, nodes=self.nodes)
        return infra_env

    def set_pull_secret(self, pull_secret: str, cluster_id: str = None):
        log.info(f"Setting pull secret:{pull_secret} for cluster: {self.id}")
        self.update_config(pull_secret=pull_secret)
        self.api_client.update_cluster(cluster_id or self.id, {"pull_secret": pull_secret})

    def get_iso_download_path(self, iso_download_path: str = None):
        return iso_download_path or self._infra_env_config.iso_download_path

    def set_hostnames_and_roles(self):
        hosts = self.to_cluster_hosts(self.api_client.get_cluster_hosts(self.id))
        nodes = self.nodes.get_nodes(refresh=True)

        for host in hosts:
            node = self.find_matching_node(host, nodes)
            assert node is not None, (
                f"Failed to find matching node for host with mac address {host.macs()}"
                f" nodes: {[(n.name, n.ips, n.macs) for n in nodes]}"
            )
            self._infra_env.update_host(host_id=host.get_id(), host_role=node.role, host_name=node.name)

    def set_installer_args(self):
        hosts = self.to_cluster_hosts(self.api_client.get_cluster_hosts(self.id))
        for host in hosts:
            self._infra_env.update_host_installer_args(host_id=host.get_id())

    @staticmethod
    def to_cluster_hosts(hosts: list[dict[str, Any]]) -> list[ClusterHost]:
        return [ClusterHost(models.Host(**h)) for h in hosts]

    def find_matching_node(self, host: ClusterHost, nodes: list[Node]) -> Optional[Node]:
        # Looking for node matches the given host by its mac address (which is unique)
        for node in nodes:
            for mac in node.macs:
                if mac.lower() in host.macs():
                    return node
        return None

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
