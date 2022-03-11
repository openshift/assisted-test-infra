import os
import re
import shlex
import shutil
import sys

import pytest
import retry
import waiting
import yaml
from frozendict import frozendict
from junit_report import JunitTestCase, JunitTestSuite

import consts
from assisted_test_infra.download_logs import download_must_gather, gather_sosreport_data
from assisted_test_infra.test_infra import utils
from assisted_test_infra.test_infra.controllers.node_controllers.node_controller import NodeController
from assisted_test_infra.test_infra.helper_classes.config.controller_config import BaseNodeConfig
from assisted_test_infra.test_infra.tools.assets import LibvirtNetworkAssets
from assisted_test_infra.test_infra.utils.entity_name import ClusterName
from assisted_test_infra.test_infra.utils.oc_utils import get_operators_status
from assisted_test_infra.test_infra.utils.release_image_utils import (
    extract_installer,
    extract_rhcos_url_from_ocp_installer,
)
from service_client import SuppressAndLog, log
from tests.base_test import BaseTest
from tests.config import ClusterConfig, TerraformConfig
from triggers import get_default_triggers

BUILD_DIR = "build"
INSTALL_CONFIG_FILE_NAME = "install-config.yaml"
IBIP_DIR = os.path.join(BUILD_DIR, "ibip")
RESOURCES_DIR = os.path.join("src", "assisted_test_infra/download_logs/resources")
INSTALL_CONFIG = os.path.join(IBIP_DIR, INSTALL_CONFIG_FILE_NAME)
INSTALLER_BINARY = os.path.join(BUILD_DIR, "openshift-install")
EMBED_IMAGE_NAME = "installer-SNO-image.iso"
KUBE_CONFIG = os.path.join(IBIP_DIR, "auth", "kubeconfig")
INSTALLER_GATHER_DIR = os.path.join(IBIP_DIR, "installer-gather")
INSTALLER_GATHER_DEBUG_STDOUT = os.path.join(INSTALLER_GATHER_DIR, "gather.stdout.log")
INSTALLER_GATHER_DEBUG_STDERR = os.path.join(INSTALLER_GATHER_DIR, "gather.stderr.log")


class TestBootstrapInPlace(BaseTest):
    @JunitTestCase()
    def installer_generate(self, openshift_release_image: str):
        log.info("Installer generate ignitions")
        bip_env = {"OPENSHIFT_INSTALL_RELEASE_IMAGE_OVERRIDE": openshift_release_image}
        utils.run_command_with_output(
            f"{INSTALLER_BINARY} create single-node-ignition-config --dir={IBIP_DIR}", env=bip_env
        )

    @retry.retry(exceptions=Exception, tries=5, delay=30)
    def installer_gather(self, ip: str, ssh_key: str, out_dir: str):
        stdout, stderr, _ret = utils.run_command(
            f"{INSTALLER_BINARY} gather bootstrap --log-level debug --bootstrap {ip} --master {ip} --key {ssh_key}"
        )

        with open(INSTALLER_GATHER_DEBUG_STDOUT, "w") as f:
            f.write(stdout)

        with open(INSTALLER_GATHER_DEBUG_STDERR, "w") as f:
            f.write(stderr)

        matches = re.compile(r'.*logs captured here "(.*)".*').findall(stderr)

        if len(matches) == 0:
            log.warning(f"It seems like installer-gather didn't generate any bundles, stderr: {stderr}")
            return

        bundle_file_path, *_ = matches

        log.info(f"Found installer-gather bundle at path {bundle_file_path}")

        utils.run_command_with_output(f"tar -xzf {bundle_file_path} -C {out_dir}")
        os.remove(bundle_file_path) if os.path.exists(bundle_file_path) else None

    # ssl handshake failures at server side are not transient thus we cannot rely on curl retry mechanism by itself
    @JunitTestCase()
    @retry.retry(exceptions=Exception, tries=3, delay=30)
    def download_live_image(self, download_path: str, rhcos_url: str):
        if os.path.exists(download_path):
            log.info("Image %s already exists, skipping download", download_path)
            return

        log.info("Downloading iso to %s", download_path)
        utils.run_command(
            f"curl --location {rhcos_url} --retry 10 --retry-connrefused -o {download_path} --continue-at -"
        )

    @staticmethod
    @retry.retry(exceptions=Exception, tries=5, delay=30)
    def retrying_run_container(*args, **kwargs):
        return utils.run_container(*args, **kwargs)

    @JunitTestCase()
    def embed(self, image_name: str, ignition_file: str, embed_image_name: str) -> str:
        log.info("Embed ignition %s to iso %s", ignition_file, image_name)
        embedded_image = os.path.join(BUILD_DIR, embed_image_name)
        os.remove(embedded_image) if os.path.exists(embedded_image) else None

        flags = shlex.split("--privileged --rm -v /dev:/dev -v /run/udev:/run/udev -v .:/data -w /data")
        # retry to avoid occassional quay hiccups
        self.retrying_run_container(
            "coreos-installer",
            "quay.io/coreos/coreos-installer:release",
            flags,
            f"iso ignition embed {BUILD_DIR}/{image_name} "
            f"-f --ignition-file /data/{IBIP_DIR}/{ignition_file} -o /data/{embedded_image}",
        )

        image_path = os.path.join(consts.BASE_IMAGE_FOLDER, embed_image_name)
        shutil.move(embedded_image, image_path)
        return image_path

    def fill_install_config(
        self, pull_secret: str, ssh_pub_key: str, net_asset: LibvirtNetworkAssets, cluster_name: str
    ):
        yaml.add_representer(str, self.str_presenter)
        with open(INSTALL_CONFIG, "r") as _file:
            config = yaml.safe_load(_file)

        config["BootstrapInPlace"] = {"InstallationDisk": "/dev/vda"}
        config["pullSecret"] = pull_secret
        config["sshKey"] = ssh_pub_key
        config["metadata"]["name"] = cluster_name
        config["networking"]["machineNetwork"][0]["cidr"] = net_asset["machine_cidr"]
        config["networking"]["networkType"] = "OVNKubernetes"

        with open(INSTALL_CONFIG, "w") as _file:
            yaml.dump(config, _file)

    @JunitTestCase()
    def setup_files_and_folders(self, net_asset: LibvirtNetworkAssets, cluster_name: str):
        log.info("Creating needed files and folders")
        utils.recreate_folder(consts.BASE_IMAGE_FOLDER, force_recreate=False)
        utils.recreate_folder(IBIP_DIR, with_chmod=False, force_recreate=True)
        shutil.copy(os.path.join(RESOURCES_DIR, INSTALL_CONFIG_FILE_NAME), IBIP_DIR)
        # TODO: fetch pull_secret and ssh_key in a different way
        self.fill_install_config(os.environ["PULL_SECRET"], os.environ["SSH_PUB_KEY"], net_asset, cluster_name)

    def str_presenter(self, dumper, data):
        if "ssh-rsa" in data:  # check for multiline string
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    @pytest.fixture
    def new_cluster_configuration(self, request) -> ClusterConfig:
        return ClusterConfig(cluster_name=ClusterName(prefix="test-infra-cluster", suffix=""))

    @pytest.fixture
    def triggers(self):
        """Remove the SNO trigger on bootstrap_in_place test due to that it overrides the new_controller_configuration
        fixture values"""
        return frozendict({k: v for k, v in get_default_triggers().items() if k != "sno"})

    @pytest.fixture
    def new_controller_configuration(self, request) -> BaseNodeConfig:
        return TerraformConfig(
            masters_count=1,
            workers_count=0,
            master_memory=16 * 1024,  # in megabytes
            master_vcpu=16,
            bootstrap_in_place=True,
        )

    def all_operators_up(self) -> bool:
        try:
            statuses = get_operators_status(KUBE_CONFIG)
            if not statuses:
                log.debug("No operator has been found currently...")
                return False

            invalid_operators = [operator for operator, up in statuses.items() if not up]

            all_operators_are_valid = len(invalid_operators) == 0

            if not all_operators_are_valid:
                log.debug("Following operators are still down: %s", ", ".join(invalid_operators))

            return all_operators_are_valid
        except Exception as e:
            print("got exception while validating operators: %s", e)
            return False

    @JunitTestCase()
    def log_collection(self, vm_ip: str):
        etype, _value, _tb = sys.exc_info()

        log.info(f"Collecting logs after a {('failed', 'successful')[etype is None]} installation")

        with SuppressAndLog(Exception):
            log.info("Gathering sosreport data from host...")
            gather_sosreport_data(output_dir=IBIP_DIR)

        with SuppressAndLog(Exception):
            log.info("Gathering information via installer-gather...")
            utils.recreate_folder(INSTALLER_GATHER_DIR, force_recreate=True)
            self.installer_gather(ip=vm_ip, ssh_key=consts.DEFAULT_SSH_PRIVATE_KEY_PATH, out_dir=INSTALLER_GATHER_DIR)

        with SuppressAndLog(Exception):
            log.info("Gathering information via must-gather...")
            download_must_gather(KUBE_CONFIG, IBIP_DIR)

    @JunitTestCase()
    def waiting_for_installation_completion(self, controller: NodeController):
        vm_ip = controller.master_ips[0][0]

        try:
            log.info("Configuring /etc/hosts...")
            utils.config_etc_hosts(
                cluster_name=controller.cluster_name, base_dns_domain=controller.cluster_domain, api_vip=vm_ip
            )

            log.info("Waiting for installation to complete...")
            waiting.wait(
                self.all_operators_up, sleep_seconds=20, timeout_seconds=60 * 60, waiting_for="all operators to get up"
            )
            log.info("Installation completed successfully!")

        finally:
            self.log_collection(vm_ip)

    @JunitTestSuite()
    def test_bootstrap_in_place(
        self, controller: NodeController, controller_configuration: BaseNodeConfig, cluster_configuration: ClusterConfig
    ):
        openshift_release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")
        if not openshift_release_image:
            raise ValueError("os env OPENSHIFT_INSTALL_RELEASE_IMAGE must be provided")

        self.setup_files_and_folders(controller_configuration.net_asset, cluster_configuration.cluster_name.get())

        extract_installer(openshift_release_image, BUILD_DIR)
        self.installer_generate(openshift_release_image)

        self.download_live_image(
            f"{BUILD_DIR}/installer-image.iso", extract_rhcos_url_from_ocp_installer(INSTALLER_BINARY)
        )
        image_path = self.embed("installer-image.iso", "bootstrap-in-place-for-live-iso.ign", EMBED_IMAGE_NAME)

        log.info("Starting node...")
        controller.image_path = image_path
        controller.start_all_nodes()
        log.info("Node started!")

        self.waiting_for_installation_completion(controller)
