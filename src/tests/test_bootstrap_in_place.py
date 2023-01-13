import base64
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import jinja2
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
from assisted_test_infra.test_infra.controllers.node_controllers.terraform_controller import TerraformController
from assisted_test_infra.test_infra.helper_classes.config.base_nodes_config import BaseNodesConfig
from assisted_test_infra.test_infra.tools.assets import LibvirtNetworkAssets
from assisted_test_infra.test_infra.utils.entity_name import ClusterName
from assisted_test_infra.test_infra.utils.oc_utils import (
    approve_csr,
    get_clusteroperators_status,
    get_nodes_readiness,
    get_unapproved_csr_names,
)
from assisted_test_infra.test_infra.utils.release_image_utils import (
    extract_installer,
    extract_rhcos_url_from_ocp_installer,
)
from service_client import SuppressAndLog, log
from tests.base_test import BaseTest
from tests.config import ClusterConfig, TerraformConfig
from triggers import get_default_triggers

CLUSTER_PREFIX = "test-infra-cluster"
INSTALLATION_DISK = "/dev/vda"
BUILD_DIR = "build"
INSTALL_CONFIG_FILE_NAME = "install-config.yaml"
WORKER_INSTALL_SCRIPT = "sno-worker-install.sh"
WORKER_LIVE_IGNITION_TEMPLATE = "sno-worker-live.ign.j2"
IBIP_DIR = os.path.join(BUILD_DIR, "ibip")
RESOURCES_DIR = os.path.join("src", "assisted_test_infra/resources/bootstrap_in_place")
INSTALL_CONFIG = os.path.join(IBIP_DIR, INSTALL_CONFIG_FILE_NAME)
INSTALLER_BINARY = os.path.join(BUILD_DIR, "openshift-install")
EMBED_IMAGE_NAME = "installer-SNO-image.iso"
EMBED_IMAGE_NAME_WORKER = "worker-image.iso"
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
    def installer_gather(self, ip: str, ssh_key: Path, out_dir: str):
        stdout, stderr, _ret = utils.run_command(
            f"{INSTALLER_BINARY} gather bootstrap --log-level debug --bootstrap {ip} --master {ip} --key {str(ssh_key)}"
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
        utils.download_file(rhcos_url, download_path, verify_ssl=False)

    @staticmethod
    @retry.retry(exceptions=Exception, tries=5, delay=30)
    def retrying_run_container(*args, **kwargs):
        return utils.run_container(*args, **kwargs)

    @JunitTestCase()
    def embed(self, image_name: str, ignition_file: str, embed_image_name: str) -> str:
        log.info("Embed ignition %s to iso %s", ignition_file, image_name)
        embedded_image = os.path.join(BUILD_DIR, embed_image_name)
        os.remove(embedded_image) if os.path.exists(embedded_image) else None

        flags = shlex.split(f"--privileged --rm -v /dev:/dev -v /run/udev:/run/udev -v {os.getcwd()}:/data -w /data")
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

        config["BootstrapInPlace"] = {"InstallationDisk": INSTALLATION_DISK}
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
        return ClusterConfig(cluster_name=ClusterName(prefix=CLUSTER_PREFIX, suffix=""))

    @pytest.fixture
    def triggers(self):
        """
        Remove the SNO trigger on bootstrap_in_place test due to that it
        overrides the new_controller_configuration fixture values
        """
        return frozendict({k: v for k, v in get_default_triggers().items() if k != "sno"})

    @pytest.fixture
    def new_controller_configuration(self, request) -> BaseNodesConfig:
        # Adjust the Terraform configuration according to whether we're
        # doing SNO or SNO + Worker
        if request.function == self.test_bootstrap_in_place_sno:
            return TerraformConfig(
                masters_count=1,
                workers_count=0,
                master_memory=16 * consts.MiB_UNITS,
                master_vcpu=16,
                bootstrap_in_place=True,
            )
        elif request.function == self.test_bip_add_worker:
            return TerraformConfig(
                masters_count=1,
                workers_count=1,
                master_memory=16 * consts.MiB_UNITS,
                master_vcpu=16,
                worker_memory=8 * consts.MiB_UNITS,
                worker_vcpu=16,
                bootstrap_in_place=True,
                running=False,
            )
        else:
            raise ValueError(f"Unexpected test {request.function}")

    @staticmethod
    def all_operators_available() -> bool:
        try:
            operator_statuses = get_clusteroperators_status(KUBE_CONFIG)
        except subprocess.SubprocessError:
            log.debug("Failed to get cluster operators status. This is usually due to API downtime. Retrying")
            return False

        if len(operator_statuses) == 0:
            log.debug("List of operators seems to still be empty... Retrying")
            return False

        if not all(available for available in operator_statuses.values()):
            log.debug(
                "Following operators are still down: %s",
                ", ".join(operator for operator, available in operator_statuses.items() if not available),
            )
            return False

        return True

    @JunitTestCase()
    def log_collection(self, master_ip: Optional[str]):
        """
        Collects all sorts of logs about the installation process

        @param master_ip The IP address of the master node. Used to SSH into the node when doing installer gather.
                         When not given, installer gather log collection is skipped.
        """
        etype, _value, _tb = sys.exc_info()

        log.info(f"Collecting logs after a {('failed', 'successful')[etype is None]} installation")

        with SuppressAndLog(Exception):
            log.info("Gathering sosreport data from host...")
            gather_sosreport_data(output_dir=IBIP_DIR)

        if master_ip is not None:
            with SuppressAndLog(Exception):
                log.info("Gathering information via installer-gather...")
                utils.recreate_folder(INSTALLER_GATHER_DIR, force_recreate=True)
                self.installer_gather(
                    ip=master_ip, ssh_key=consts.DEFAULT_SSH_PRIVATE_KEY_PATH, out_dir=INSTALLER_GATHER_DIR
                )

        with SuppressAndLog(Exception):
            log.info("Gathering information via must-gather...")
            download_must_gather(KUBE_CONFIG, IBIP_DIR)

    @JunitTestCase()
    def waiting_for_installation_completion(
        self, controller: NodeController, cluster_configuration: ClusterConfig, skip_logs=False
    ):
        master_ip = controller.master_ips[0][0]

        try:
            log.info("Configuring /etc/hosts...")
            utils.config_etc_hosts(
                cluster_name=cluster_configuration.cluster_name.get(),
                base_dns_domain=cluster_configuration.base_dns_domain,
                api_vip=master_ip,
            )

            log.info("Waiting for installation to complete...")
            waiting.wait(
                self.all_operators_available,
                sleep_seconds=20,
                timeout_seconds=70 * 60,
                waiting_for="all operators to get up",
            )
            log.info("Installation completed successfully!")
        except Exception:
            log.exception("An unexpected error has occurred while waiting for installation to complete")
            # In case of error, always collect logs
            self.log_collection(master_ip)
            raise
        else:
            # If successful, collect logs only if caller asked not to skip
            if not skip_logs:
                self.log_collection(master_ip)

    def inject_bootstrap(self, ignition_filename: str, butane_config: str):
        # Backup bip ignition file to bootstrap_initial.ign
        initial_ignition = os.path.join(IBIP_DIR, ignition_filename)
        backup_ignition = os.path.join(IBIP_DIR, "bootstrap_initial.ign")
        shutil.move(initial_ignition, backup_ignition)
        flags = shlex.split(f"--rm -v {os.getcwd()}:/data -w /data")
        # Patch ignition with additional files and services
        self.retrying_run_container(
            "butane",
            "quay.io/coreos/butane:release",
            flags,
            f"/data/{IBIP_DIR}/{butane_config}",
            f"-o /data/{initial_ignition}",
        )

    def prepare_installation(self, controller_configuration: BaseNodesConfig, cluster_configuration: ClusterConfig):
        openshift_release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")
        if not openshift_release_image:
            raise ValueError("os env OPENSHIFT_INSTALL_RELEASE_IMAGE must be provided")

        self.setup_files_and_folders(controller_configuration.net_asset, cluster_configuration.cluster_name.get())

        extract_installer(openshift_release_image, BUILD_DIR)
        self.installer_generate(openshift_release_image)

        ignition_filename = "bootstrap-in-place-for-live-iso.ign"
        bip_butane_config = os.environ.get("BOOTSTRAP_INJECT_MANIFEST")
        if bip_butane_config:
            self.inject_bootstrap(ignition_filename, bip_butane_config)

        self.download_live_image(
            f"{BUILD_DIR}/installer-image.iso", extract_rhcos_url_from_ocp_installer(INSTALLER_BINARY)
        )
        return self.embed("installer-image.iso", ignition_filename, EMBED_IMAGE_NAME)

    @JunitTestSuite()
    def test_bootstrap_in_place_sno(
        self,
        controller: NodeController,
        controller_configuration: BaseNodesConfig,
        cluster_configuration: ClusterConfig,
    ):
        image_path = self.prepare_installation(controller_configuration, cluster_configuration)

        log.info("Starting node...")
        cluster_configuration.iso_download_path = image_path
        controller.start_all_nodes()
        log.info("Node started!")

        controller.start_all_nodes()
        self.waiting_for_installation_completion(controller, cluster_configuration)

    @staticmethod
    def render_worker_live_iso_ignition(install_device: str):
        """
        The worker live iso ignition file is embedded in the live ISO for the worker
        and is responsible for:
            - Copying the worker.ign file into the live filesystem
            - Creating a one-shot systemd unit service which runs coreos-installer with the worker.ign
            - Rebooting the node once the operating system has been written to disk

        The worker then starts with the installed RHCOS+worker.ign and attempts to join the cluster

        The reason we don't simply boot the live ISO with the worker.ign as
        ignition is because an RHCOS OS with worker.ign has to be written to
        disk, worker.ign is not meant to be the ignition of the live ISO
        itself. Basically, the live ISO phase is just a temporary operating
        system for the user to shell into and run coreos-installer to install
        the actual operating system used for OCP. In this test we just automate
        this manual process using our own ignition file, which will
        automatically run coreos-installer within the live operating system and
        reboot the node for us.

        @param install_device The path of the disk to install RHCOS on (e.g. /dev/vda)
        """
        with open(os.path.join(RESOURCES_DIR, WORKER_LIVE_IGNITION_TEMPLATE), "r") as f:
            live_iso_ignition_template_contents = f.read()

        with open(os.path.join(RESOURCES_DIR, WORKER_INSTALL_SCRIPT), "rb") as f:
            worker_install_script_contents = f.read()

        try:
            with open(os.path.join(IBIP_DIR, "worker.ign"), "rb") as f:
                worker_ignition_contents = f.read()
        except FileNotFoundError:
            log.error(
                "The worker.ign file is only generated in OCP 4.11 and above, "
                "this test is not meant to run on earlier versions"
            )
            raise

        jinja2.filters.FILTERS["b64encode_utf8"] = lambda s: base64.b64encode(s).decode("utf-8")

        return jinja2.Template(live_iso_ignition_template_contents).render(
            ssh_public_key=os.environ["SSH_PUB_KEY"],
            worker_ign_contents=worker_ignition_contents,
            install_sh_contents=worker_install_script_contents,
            install_device=install_device,
        )

    @staticmethod
    def worker_ready() -> bool:
        try:
            node_readiness_map = get_nodes_readiness(KUBE_CONFIG)
        except subprocess.SubprocessError:
            log.debug("Failed to list nodes. This is usually due to API downtime. Retrying")
            return False

        if f"{CLUSTER_PREFIX}-master-0" not in node_readiness_map:
            log.warning("Couldn't find master in node status list, this should not happen")
            return False

        if f"{CLUSTER_PREFIX}-worker-0" not in node_readiness_map:
            return False

        return all(node_status for node_status in node_readiness_map.values())

    @JunitTestCase()
    def waiting_for_added_worker(self, controller: NodeController):
        try:
            log.info("Waiting for worker to be added...")
            waiting.wait(
                self.worker_ready, sleep_seconds=20, timeout_seconds=60 * 60, waiting_for="worker node to be ready"
            )
            log.info("Day 2 worker addition finished successfully!")
        finally:
            # Use None master_ip because we don't care about installer-gather at this stage
            self.log_collection(master_ip=None)

    @staticmethod
    def approve_csrs(kubeconfig_path: str, done: threading.Event):
        log.info("Started background worker to approve CSRs when they appear...")
        while not done.is_set():
            unapproved_csrs = []
            try:
                unapproved_csrs = get_unapproved_csr_names(kubeconfig_path)
            except subprocess.SubprocessError:
                log.debug("Failed to list csrs. This is usually due to API downtime. Retrying")
            except Exception:
                # We're in a thread so it's a bit awkward to stop everything else...
                # Just continue after logging the unexpected exception
                log.exception("Unknown exception while listing csrs")

            for csr_name in unapproved_csrs:
                log.info(f"Found unapproved CSR {csr_name}, approving...")

                try:
                    approve_csr(kubeconfig_path, csr_name)
                except subprocess.SubprocessError:
                    log.warning("Failed attempt to approve CSR, this may be due to API downtime. Will retry later")
                except Exception:
                    # We're in a thread so it's a bit awkward to stop everything else...
                    # Just continue after logging the unexpected exception
                    log.exception(f"Unknown exception while approving the {csr_name} CSR")

            time.sleep(10)

    @JunitTestCase()
    def prepare_worker_installation(
        self,
        controller_configuration: BaseNodesConfig,
        cluster_configuration: ClusterConfig,
        master_image_path: str,
    ):
        cluster_configuration.iso_download_path = master_image_path

        with open(os.path.join(IBIP_DIR, "worker-live-iso.ign"), "w") as f:
            f.write(self.render_worker_live_iso_ignition(INSTALLATION_DISK))

        worker_image_path = self.embed("installer-image.iso", "worker-live-iso.ign", EMBED_IMAGE_NAME_WORKER)
        cluster_configuration.worker_iso_download_path = worker_image_path

    @JunitTestCase()
    def master_installation(self, controller: TerraformController, cluster_configuration: ClusterConfig):
        log.info("Starting master node...")
        controller.start_node(node_name=f"{CLUSTER_PREFIX}-master-0")

        self.waiting_for_installation_completion(controller, cluster_configuration, skip_logs=True)

    @JunitTestCase()
    def worker_installation(self, controller: TerraformController, cluster_configuration: ClusterConfig):
        controller.start_node(node_name=f"{CLUSTER_PREFIX}-worker-0")

        # Start a background worker to approve CSRs
        approve_csr_worker_done = threading.Event()
        approve_csr_worker = threading.Thread(
            target=self.approve_csrs,
            args=(KUBE_CONFIG, approve_csr_worker_done),
            # Don't hang if this thread is still running for some reason
            daemon=True,
        )

        approve_csr_worker.start()

        try:
            self.waiting_for_added_worker(controller)
        finally:
            approve_csr_worker_done.set()

        approve_csr_worker.join(timeout=10)
        if approve_csr_worker.is_alive():
            log.warning("CSR thread is still running for some reason")

    @JunitTestSuite()
    def test_bip_add_worker(
        self,
        controller: TerraformController,
        controller_configuration: BaseNodesConfig,
        cluster_configuration: ClusterConfig,
    ):
        master_image_path = self.prepare_installation(controller_configuration, cluster_configuration)
        self.prepare_worker_installation(controller_configuration, cluster_configuration, master_image_path)
        controller._create_nodes()
        self.master_installation(controller, cluster_configuration)
        self.worker_installation(controller, cluster_configuration)
