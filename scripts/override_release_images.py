#!/usr/bin/python3
# -*- coding: utf-8 -*-
from argparse import ArgumentParser
from contextlib import contextmanager

import json
import os
import shlex
import subprocess
import tempfile

import semver


@contextmanager
def pull_secret_file():
    pull_secret = os.environ.get("PULL_SECRET")

    try:
        json.loads(pull_secret)
    except json.JSONDecodeError as e:
        raise ValueError("Value of PULL_SECRET environment variable is not a valid JSON payload") from e

    with tempfile.NamedTemporaryFile(mode="w") as f:
        f.write(pull_secret)
        f.flush()
        yield f.name


def run_command(command, shell=False, raise_errors=True, env=None):
    command = command if shell else shlex.split(command)
    process = subprocess.run(
        command, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, universal_newlines=True
    )

    def _io_buffer_to_str(buf):
        if hasattr(buf, "read"):
            buf = buf.read().decode()
        return buf

    out = _io_buffer_to_str(process.stdout).strip()
    err = _io_buffer_to_str(process.stderr).strip()

    if raise_errors and process.returncode != 0:
        raise RuntimeError(f"command: {command} exited with an error: {err} " f"code: {process.returncode}")

    return out, err, process.returncode


def get_full_openshift_version_from_release(release_image: str) -> str:
    with pull_secret_file() as pull_secret:
        stdout, _, _ = run_command(
            f"oc adm release info '{release_image}' --registry-config '{pull_secret}' -o json |"
            f" jq -r '.metadata.version'",
            shell=True,
        )
    return stdout


def get_release_image(release_images, ocp_version, cpu_architecture="x86_64"):
    archs_images = [v for v in release_images if v.get('cpu_architecture') == cpu_architecture]
    release_image = [v for v in archs_images if v.get('openshift_version') == ocp_version]
    if len(release_image) >= 1:
        return release_image[0]

    return {"cpu_architecture": cpu_architecture}


def set_release_image(release_image: dict, release_images: list, ocp_version, ocp_full_version):
    release_image_index = -1 if "openshift_version" not in release_image else release_images.index(release_image)

    release_image["openshift_version"] = ocp_version
    release_image["url"] = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")
    release_image["version"] = ocp_full_version
    if release_image_index != -1:
        release_images[release_image_index] = release_image
    else:
        release_images.append(release_image)


def main():
    # Load default release images
    with open(args.src, 'r') as f:
        release_images: list = json.load(f)

    release_image = os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE")
    ocp_full_version = get_full_openshift_version_from_release(release_image)
    ocp_semver = semver.VersionInfo.parse(ocp_full_version)
    ocp_version = "{}.{}".format(ocp_semver.major, ocp_semver.minor)

    # Find relevant release image
    release_image = get_release_image(release_images, ocp_version)
    set_release_image(release_image, release_images, ocp_version, ocp_full_version)

    # Store release images
    json.dump(release_images, os.sys.stdout, separators=(',', ':'))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        '--src',
        type=str,
        help='Release images list file path'
    )
    args = parser.parse_args()
    main()
