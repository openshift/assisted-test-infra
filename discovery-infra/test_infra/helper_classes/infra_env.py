import os
import logging
from typing import Optional
from junit_report import JunitTestCase
from test_infra import consts, utils
from test_infra.assisted_service_api import InventoryClient
from test_infra.helper_classes.config import BaseInfraEnvConfig
from test_infra.helper_classes.nodes import Nodes
from test_infra.tools import static_network, terraform_utils


class InfraEnv:
    def __init__(self, api_client: InventoryClient, config: BaseInfraEnvConfig, nodes: Optional[Nodes] = None):
        self._config = config
        self.nodes = nodes
        self.api_client = api_client
        try:
            infra_env = self._create()
        except BaseException:
            logging.exception("create")
            raise
        self._config.infra_env_id = self.id = infra_env.id

    def _create(self):
        return self.api_client.create_infra_env(
            self._config.entity_name.get(),
            pull_secret=self._config.pull_secret,
            ssh_public_key=self._config.ssh_public_key,
            openshift_version=self._config.openshift_version,
        )

    @property
    def config(self):
        return self._config.get_copy()

    def update_config(self, **kwargs):
        """
        Note that kwargs can contain values for overriding BaseInfraEnvConfig arguments.
        The name (key) of each argument must match to one of the BaseInfraEnvConfig arguments.
        If key doesn't exists in config - KeyError exception is raised
        """
        logging.info(f"Updating infra-env {self.id} configurations to {kwargs}")

        for k, v in kwargs.items():
            if not hasattr(self._config, k):
                raise KeyError(f"The key {k} is not present in {self._config.__class__.__name__}")
            setattr(self._config, k, v)

    def prepare_infraenv(self, **kwargs):
        self.update_config(**kwargs)
        logging.info(f"Preparing for installation with infra-env configurations: infraenv_config={self._config}")
        self.nodes.controller.log_configuration()
        if self._config.download_image:
            self.download_image(
                iso_download_path=self._config.iso_download_path,
            )

        self.nodes.notify_iso_ready()
        self.nodes.start_all(self._config.is_static_ip)
        self.wait_until_hosts_are_discovered(allow_insufficient=True)

    @JunitTestCase()
    def download_image(self, iso_download_path=None):
        iso_download_path = iso_download_path or self._config.iso_download_path

        # ensure file path exists before downloading
        if not os.path.exists(iso_download_path):
            utils.recreate_folder(os.path.dirname(iso_download_path), force_recreate=False)

        self.api_client.download_infraenv_image(
            infraenv_id=self.id,
            image_path=iso_download_path,
        )

    @JunitTestCase()
    def wait_until_hosts_are_discovered(self, nodes_count: int, allow_insufficient=False):
        statuses = [consts.NodesStatus.KNOWN_UNBOUND]
        if allow_insufficient:
            statuses.append(consts.NodesStatus.INSUFFICIENT_UNBOUND)
        utils.wait_till_all_infra_env_hosts_are_in_status(
            client=self.api_client,
            infra_env_id=self.id,
            nodes_count=nodes_count,
            statuses=statuses,
            timeout=consts.NODES_REGISTERED_TIMEOUT,
        )
