import logging
import os
import re
import shlex
import shutil
import sys

import waiting
import yaml
from test_infra import utils, consts, warn_deprecate
from test_infra.tools.assets import LibvirtNetworkAssets
from test_infra.controllers.node_controllers.terraform_controller import TerraformController

from download_logs import download_must_gather, gather_sosreport_data
from oc_utils import get_operators_status
from test_infra.utils.cluster_name import ClusterName
from tests.config import TerraformConfig, ClusterConfig

warn_deprecate()


BUILD_DIR = "build"
INSTALL_CONFIG_FILE_NAME = "install-config.yaml"
IBIP_DIR = os.path.join(BUILD_DIR, "ibip")
RESOURCES_DIR = os.path.join("discovery-infra", "resources")
INSTALL_CONFIG = os.path.join(IBIP_DIR, INSTALL_CONFIG_FILE_NAME)
INSTALLER_BINARY = os.path.join(BUILD_DIR, "openshift-install")
EMBED_IMAGE_NAME = "installer-SNO-image.iso"
KUBE_CONFIG = os.path.join(IBIP_DIR, "auth", "kubeconfig")
MUST_GATHER_DIR = os.path.join(IBIP_DIR, "must-gather")
INSTALLER_GATHER_DIR = os.path.join(IBIP_DIR, "installer-gather")
INSTALLER_GATHER_DEBUG_STDOUT = os.path.join(INSTALLER_GATHER_DIR, "gather.stdout.log")
INSTALLER_GATHER_DEBUG_STDERR = os.path.join(INSTALLER_GATHER_DIR, "gather.stderr.log")
SSH_KEY = os.path.join("ssh_key", "key")


def installer_generate(openshift_release_image):
    logging.info("Installer generate ignitions")
    bip_env = {"OPENSHIFT_INSTALL_RELEASE_IMAGE_OVERRIDE": openshift_release_image}
    utils.run_command_with_output(f"{INSTALLER_BINARY} create single-node-ignition-config --dir={IBIP_DIR}",
                                  env=bip_env)


@utils.retry(exceptions=Exception, tries=5, delay=30)
def installer_gather(ip, ssh_key, out_dir):
    stdout, stderr, _ret = utils.run_command(
        f"{INSTALLER_BINARY} gather bootstrap --log-level debug --bootstrap {ip} --master {ip} --key {ssh_key}"
    )

    with open(INSTALLER_GATHER_DEBUG_STDOUT, "w") as f:
        f.write(stdout)

    with open(INSTALLER_GATHER_DEBUG_STDERR, "w") as f:
        f.write(stderr)

    matches = re.compile(r'.*logs captured here "(.*)".*').findall(stderr)

    if len(matches) == 0:
        logging.warning(f"It seems like installer-gather didn't generate any bundles, stderr: {stderr}")
        return

    bundle_file_path, *_ = matches

    logging.info(f"Found installer-gather bundle at path {bundle_file_path}")

    utils.run_command_with_output(f"tar -xzf {bundle_file_path} -C {out_dir}")
    os.remove(bundle_file_path) if os.path.exists(bundle_file_path) else None


def download_live_image(download_path):
    if os.path.exists(download_path):
        logging.info("Image %s already exists, skipping download", download_path)
        return

    logging.info("Downloading iso to %s", download_path)
    # TODO: enable fetching the appropriate rhcos image
    utils.run_command(
        f"curl https://mirror.openshift.com/pub/openshift-v4/dependencies/rhcos/pre-release/"
        f"4.7.0-rc.2/rhcos-4.7.0-rc.2-x86_64-live.x86_64.iso --retry 5 -o {download_path}")


def embed(image_name, ignition_file, embed_image_name):
    logging.info("Embed ignition %s to iso %s", ignition_file, image_name)
    embedded_image = os.path.join(BUILD_DIR, embed_image_name)
    os.remove(embedded_image) if os.path.exists(embedded_image) else None

    flags = shlex.split("--privileged --rm -v /dev:/dev -v /run/udev:/run/udev -v .:/data -w /data")
    utils.run_container("coreos-installer", "quay.io/coreos/coreos-installer:release", flags,
                        f"iso ignition embed {BUILD_DIR}/{image_name} "
                        f"-f --ignition-file /data/{IBIP_DIR}/{ignition_file} -o /data/{embedded_image}")

    image_path = os.path.join(consts.BASE_IMAGE_FOLDER, embed_image_name)
    shutil.move(embedded_image, image_path)
    return image_path


def fill_install_config(pull_secret, ssh_pub_key, net_asset, cluster_name):
    yaml.add_representer(str, str_presenter)
    with open(INSTALL_CONFIG, "r") as _file:
        config = yaml.safe_load(_file)

    config["BootstrapInPlace"] = {"InstallationDisk": "/dev/vda"}
    config["pullSecret"] = pull_secret
    config["sshKey"] = ssh_pub_key
    config["metadata"]["name"] = cluster_name
    config["networking"]["machineNetwork"][0]["cidr"] = net_asset["machine_cidr"]

    with open(INSTALL_CONFIG, "w") as _file:
        yaml.dump(config, _file)


def setup_files_and_folders(args, net_asset, cluster_name):
    logging.info("Creating needed files and folders")
    utils.recreate_folder(consts.BASE_IMAGE_FOLDER, force_recreate=False)
    utils.recreate_folder(IBIP_DIR, with_chmod=False, force_recreate=True)
    shutil.copy(os.path.join(RESOURCES_DIR, INSTALL_CONFIG_FILE_NAME), IBIP_DIR)
    fill_install_config(args.pull_secret, args.ssh_key, net_asset, cluster_name)


def str_presenter(dumper, data):
    if "ssh-rsa" in data:  # check for multiline string
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def create_controller(net_asset):
    return TerraformController(
        TerraformConfig(
            masters_count=1,
            workers_count=0,
            master_memory=45 * 1024,  # in megabytes
            master_vcpu=16,
            net_asset=net_asset,
            bootstrap_in_place=True,
            single_node_ip=net_asset.machine_cidr.replace("0/24", "10"),
        ),
        cluster_config=ClusterConfig(cluster_name=ClusterName(prefix="test-infra-cluster", suffix=""))
    )


def all_operators_up():
    try:
        statuses = get_operators_status(KUBE_CONFIG)
        if not statuses:
            logging.debug("No operator has been found currently...")
            return False

        invalid_operators = [operator for operator, up in statuses.items() if not up]

        all_operators_are_valid = len(invalid_operators) == 0

        if not all_operators_are_valid:
            logging.debug("Following operators are still down: %s", ", ".join(invalid_operators))

        return all_operators_are_valid
    except Exception as e:
        print("got exception while validating operators: %s", e)
        return False


# noinspection PyBroadException
def log_collection(vm_ip):
    etype, _value, _tb = sys.exc_info()

    logging.info(f"Collecting logs after a {('failed', 'successful')[etype is None]} installation")

    try:
        logging.info("Gathering sosreport data from host...")
        gather_sosreport_data(output_dir=IBIP_DIR, private_ssh_key_path=SSH_KEY)
    except Exception:
        logging.exception("sosreport gathering failed!")

    utils.retry()
    try:
        logging.info("Gathering information via installer-gather...")
        utils.recreate_folder(INSTALLER_GATHER_DIR, force_recreate=True)
        installer_gather(ip=vm_ip, ssh_key=SSH_KEY, out_dir=INSTALLER_GATHER_DIR)
    except Exception:
        logging.exception("installer-gather failed!")

    try:
        logging.info("Gathering information via must-gather...")
        utils.recreate_folder(MUST_GATHER_DIR)
        download_must_gather(KUBE_CONFIG, MUST_GATHER_DIR)
    except Exception:
        logging.exception("must-gather failed!")


def waiting_for_installation_completion(controller):
    vm_ip = controller.master_ips[0][0]

    try:
        logging.info("Configuring /etc/hosts...")
        utils.config_etc_hosts(cluster_name=controller.cluster_name,
                               base_dns_domain=controller.cluster_domain,
                               api_vip=vm_ip)

        logging.info("Waiting for installation to complete...")
        waiting.wait(all_operators_up,
                     sleep_seconds=20,
                     timeout_seconds=60 * 60,
                     waiting_for="all operators to get up")
        logging.info("Installation completed successfully!")
    finally:
        log_collection(vm_ip)


def execute_ibip_flow(args):
    openshift_release_image = os.getenv('OPENSHIFT_INSTALL_RELEASE_IMAGE')
    if not openshift_release_image:
        raise ValueError("os env OPENSHIFT_INSTALL_RELEASE_IMAGE must be provided")

    net_asset = LibvirtNetworkAssets().get()
    controller = create_controller(net_asset)
    setup_files_and_folders(args, net_asset, controller.cluster_name)

    utils.extract_installer(openshift_release_image, BUILD_DIR)
    installer_generate(openshift_release_image)

    download_live_image(f"{BUILD_DIR}/installer-image.iso")
    image_path = embed("installer-image.iso", "bootstrap-in-place-for-live-iso.ign", EMBED_IMAGE_NAME)

    logging.info("Starting node...")
    controller.image_path = image_path
    controller.start_all_nodes()
    logging.info("Node started!")

    waiting_for_installation_completion(controller)
