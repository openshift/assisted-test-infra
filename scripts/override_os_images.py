#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
from argparse import ArgumentParser

import consts
from assisted_test_infra.test_infra import utils


def get_os_image(os_images, ocp_version, cpu_architecture="x86_64"):
    archs_images = [v for v in os_images if v.get("cpu_architecture") == cpu_architecture]
    os_images = [v for v in archs_images if v.get("openshift_version") == ocp_version]
    if len(os_images) >= 1:
        return os_images[0]

    return archs_images[-1]


def extract_version(release_image: str) -> str:
    if not release_image:
        return ""

    full_ocp_version = utils.extract_version(release_image)
    return f"{full_ocp_version.major}.{full_ocp_version.minor}"


def main():
    # Load default os images
    with open(args.src, "r") as f:
        os_images: list = json.load(f)

    # Load override images
    if os.getenv("OS_IMAGES") is not None:
        os_images_override: list = json.loads(os.getenv("OS_IMAGES"))
        for image in os_images:
            image_version = image["openshift_version"]
            for override_image in os_images_override:
                if override_image["openshift_version"] == image_version:
                    image.update(override_image)
                    break

    if os.getenv("RELEASE_IMAGES") is not None:
        release_images = json.loads(os.getenv("RELEASE_IMAGES"))
        latest_ocp_version = release_images[-1]["openshift_version"]

        # If OS image for latest OCP versions doesn't exists, clone latest OS image and override 'openshift_version'
        os_image = get_os_image(os_images, latest_ocp_version)
        if os_image["openshift_version"] != latest_ocp_version:
            new_image = os_image.copy()
            new_image["openshift_version"] = latest_ocp_version
            new_image["version"] = f"{os_image['openshift_version']}-assisted-override"
            os_images.append(new_image)

    # keeping only images for relevant openshift versions
    openshift_version = (
        os.environ.get("OPENSHIFT_VERSION")
        or extract_version(os.environ.get("OPENSHIFT_INSTALL_RELEASE_IMAGE"))
        or consts.OpenshiftVersion.DEFAULT.value
    )

    os_images = [
        image
        for image in os_images
        if image["cpu_architecture"] not in ["s390x", "ppc64le"] and image["openshift_version"] == openshift_version
    ]

    json.dump(os_images, os.sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--src", type=str, help="OS images list file path")
    args = parser.parse_args()
    main()
