import json
import logging

import semver

from assisted_test_infra.test_infra import utils


def extract_installer(release_image: str, dest: str):
    """
    Extracts the installer binary from the release image.

    Args:
        release_image: The release image to extract the installer from.
        dest: The destination to extract the installer to.
    """
    logging.info("Extracting installer from %s to %s", release_image, dest)
    with utils.pull_secret_file() as pull_secret:
        utils.run_command(
            f"oc adm release extract --registry-config '{pull_secret}'"
            f" --command=openshift-install --to={dest} {release_image}"
        )


def extract_version(release_image):
    """
    Extracts the version number from the release image.

    Args:
        release_image: The release image to extract the version from.
    """
    logging.info(f"Extracting version number from {release_image}")
    with utils.pull_secret_file() as pull_secret:
        stdout, _, _ = utils.run_command(
            f"oc adm release info --registry-config '{pull_secret}' '{release_image}' -ojson"
        )

    ocp_full_version = json.loads(stdout).get("metadata", {}).get("version", "")
    ocp_semver = semver.VersionInfo.parse(ocp_full_version)
    ocp_version = f"{ocp_semver.major}.{ocp_semver.minor}"

    return ocp_version


def extract_rhcos_url_from_ocp_installer(installer_binary_path: str):
    """
    Extracts the RHCOS download URL from the installer binary.

    Args:
        installer_binary_path: The path to the installer binary.
    """
    logging.info(f"Extracting RHCOS URL from {installer_binary_path}")
    stdout, _, _ = utils.run_command(f"'{installer_binary_path}' coreos print-stream-json")

    jsonpath = "architectures.x86_64.artifacts.metal.formats.iso.disk.location"
    current_node = json.loads(stdout)
    for element in jsonpath.split("."):
        current_node = current_node.get(element, {})

    if current_node == {}:
        raise ValueError(f"Could not extract RHCOS URL from {installer_binary_path}, malformed JSON")

    logging.info(f"Extracted RHCOS URL: {current_node}")

    return current_node
