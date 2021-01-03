import os
import shutil
import shlex
import logging
import yaml

import waiting

from oc_utils import get_operators_status
from download_logs import download_must_gather
from test_infra import utils, consts
from test_infra.tools.assets import NetworkAssets
from test_infra.helper_classes.nodes import Nodes
from test_infra.controllers.node_controllers.ssh import SshConnection
from test_infra.controllers.node_controllers.terraform_controller import TerraformController

BUILD_DIR = "build"
INSTALL_CONFIG_FILE_NAME = "install-config.yaml"
IBIP_DIR = os.path.join(BUILD_DIR, "ibip")
RESOURCES_DIR = os.path.join("discovery-infra", "resources")
INSTALL_CONFIG = os.path.join(IBIP_DIR, INSTALL_CONFIG_FILE_NAME)
INSTALLER_BINARY = os.path.join(BUILD_DIR, "openshift-install")
EMBED_IMAGE_NAME = "installer-SNO-image.iso"
KUBE_CONFIG = os.path.join(IBIP_DIR, "auth", "kubeconfig")
MUST_GATHER_DIR = os.path.join(IBIP_DIR, "must-gather")
SOSREPORT_SCRIPT = os.path.join(RESOURCES_DIR, "man_sosreport.sh")
SSH_KEY = os.path.join("ssh_key", "key")


def installer_generate(openshift_release_image):
    logging.info("Installer generate ignitions")
    bip_env={"OPENSHIFT_INSTALL_RELEASE_IMAGE": openshift_release_image,
             "OPENSHIFT_INSTALL_EXPERIMENTAL_BOOTSTRAP_IN_PLACE": "true",
             "OPENSHIFT_INSTALL_EXPERIMENTAL_BOOTSTRAP_IN_PLACE_COREOS_INSTALLER_ARGS": "/dev/vda"}
    utils.run_command_with_output(f"{INSTALLER_BINARY} create ignition-configs --dir={IBIP_DIR}", env=bip_env)


def download_live_image(download_path, rhcos_version=None):
    if os.path.exists(download_path):
        logging.info("Image %s already exists, skipping download", download_path)
        return

    logging.info("Downloading iso to %s", download_path)
    rhcos_version = rhcos_version or os.getenv('RHCOS_VERSION', "46.82.202009222340-0")
    utils.run_command(f"curl https://releases-art-rhcos.svc.ci.openshift.org/art/storage/releases/rhcos-4.6/"
                      f"{rhcos_version}/x86_64/rhcos-{rhcos_version}-live.x86_64.iso --retry 5 -o {download_path}")


def embed(image_name, ignition_file, embed_image_name):
    logging.info("Embed ignition %s to iso %s", ignition_file, image_name)
    embedded_image = os.path.join(BUILD_DIR, embed_image_name)
    os.remove(embedded_image) if os.path.exists(embedded_image) else None

    flags = shlex.split(f"--privileged --rm -v /dev:/dev -v /run/udev:/run/udev -v .:/data -w /data")
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
        cluster_name="test-infra-cluster",
        num_masters=1,
        num_workers=0,
        master_memory=32 * 1024,  # 32GB of RAM
        master_vcpu=12,
        net_asset=net_asset,
        iso_download_path="<TBD>",  # will be set later on
        bootstrap_in_place=True,
    )


def all_operators_up():
    statuses = get_operators_status(KUBE_CONFIG)
    if not statuses:
        logging.debug("No operator has been found currently...")
        return False

    invalid_operators = [operator for operator, up in statuses.items() if not up]

    all_operators_are_valid = len(invalid_operators) == 0

    if not all_operators_are_valid:
        logging.debug("Following operators are still down: %s", ", ".join(invalid_operators))

    return all_operators_are_valid


def gather_sosreport_data(node):
    node.upload_file(SOSREPORT_SCRIPT, "/tmp/man_sosreport.sh")
    node.run_command("chmod a+x /tmp/man_sosreport.sh")
    node.run_command("sudo /tmp/man_sosreport.sh")
    node.download_file("/tmp/sosreport.tar.bz2", IBIP_DIR)


def waiting_for_installation_completion(controller):
    try:
        logging.info("Configuring /etc/hosts...")
        utils.config_etc_hosts(cluster_name=controller.cluster_name,
                            base_dns_domain=controller.cluster_domain,
                            api_vip=controller.master_ips[0][0])

        logging.info("Waiting for installation to complete...")
        waiting.wait(all_operators_up,
                    sleep_seconds=20,
                    timeout_seconds=60 * 60,
                    waiting_for="all operators to get up")
        logging.info("Installation completed successfully!")

    finally:
        logging.info("Gathering sosreport data from host...")
        node = Nodes(controller, private_ssh_key_path=SSH_KEY)[0]
        gather_sosreport_data(node)

        logging.info("Gathering information via must-gather...")
        utils.recreate_folder(MUST_GATHER_DIR)
        download_must_gather(KUBE_CONFIG, MUST_GATHER_DIR)


def execute_ibip_flow(args):
    openshift_release_image = os.getenv('OPENSHIFT_INSTALL_RELEASE_IMAGE')
    if not openshift_release_image:
        raise ValueError("os env OPENSHIFT_INSTALL_RELEASE_IMAGE must be provided")

    net_asset = NetworkAssets().get()
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
