from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from assisted_service_client import models
from junit_report import JunitTestCase

import consts
from assisted_test_infra.test_infra import BaseEntityConfig
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from service_client import InventoryClient, log


class Entity(ABC):
    def __init__(self, api_client: InventoryClient, config: BaseEntityConfig, nodes: Optional[Nodes] = None):
        self._config = config
        self.api_client = api_client
        self.nodes: Nodes = nodes
        self._create() if not self.id else self.update_existing()
        self._config.iso_download_path = self.get_iso_download_path()

    @property
    @abstractmethod
    def id(self) -> str:
        pass

    @property
    def _entity_class_name(self):
        return self.__class__.__name__.lower()

    @abstractmethod
    def _create(self) -> str:
        pass

    @abstractmethod
    def update_existing(self) -> str:
        pass

    @abstractmethod
    def download_image(self, iso_download_path: str = None) -> Path:
        pass

    @abstractmethod
    def get_iso_download_path(self, iso_download_path: str = None):
        pass

    def update_config(self, **kwargs):
        """
        Note that kwargs can contain values for overriding BaseClusterConfig arguments.
        The name (key) of each argument must match to one of the BaseEntityConfig arguments.
        If key doesn't exists in config - KeyError exception is raised
        """
        log.info(f"Updating {self._entity_class_name} configurations to {kwargs}")

        for k, v in kwargs.items():
            if not hasattr(self._config, k):
                raise KeyError(f"The key {k} is not present in {self._config.__class__.__name__}")
            setattr(self._config, k, v)

    @JunitTestCase()
    def prepare_nodes(self, is_static_ip: bool = False, **kwargs):
        self.update_config(**kwargs)

        log.info(
            f"Preparing for installation with {self._entity_class_name} configurations: "
            f"{self._entity_class_name}_config={self._config}"
        )

        self.nodes.controller.log_configuration()

        if self._config.download_image and not is_static_ip:
            self.download_image()

        self.nodes.prepare_nodes()
        if is_static_ip:
            # On static IP installation re-download the image after preparing nodes and setting the
            # static IP configurations
            if self._config.download_image:
                self.download_image()

        self.nodes.notify_iso_ready()

        if self._config.ipxe_boot:
            self._set_ipxe_url()

        self.nodes.start_all(check_ips=not (is_static_ip and self._config.is_ipv6))
        self.wait_until_hosts_are_discovered(allow_insufficient=True)

    def prepare_networking(self):
        pass

    @JunitTestCase()
    def prepare_for_installation(self, **kwargs):
        self.validate_params()
        self.prepare_nodes(is_static_ip=kwargs.pop("is_static_ip", False), **kwargs)
        self.prepare_networking()

    def _set_ipxe_url(self):
        ipxe_server_url = (
            f"http://{consts.DEFAULT_IPXE_SERVER_IP}:{consts.DEFAULT_IPXE_SERVER_PORT}/{self._config.entity_name}"
        )
        self.nodes.controller.set_ipxe_url(network_name=self.nodes.get_cluster_network(), ipxe_url=ipxe_server_url)

    @abstractmethod
    def get_details(self) -> Union[models.infra_env.InfraEnv, models.cluster.Cluster]:
        pass

    @abstractmethod
    def wait_until_hosts_are_discovered(self, nodes_count: int = None, allow_insufficient=False):
        pass

    def validate_params(self):
        """
        Validate entity configuration params given by the user, do not wait to fail the test only when use those
        specific variable
        :return: None
        """
