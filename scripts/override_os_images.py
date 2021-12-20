#!/usr/bin/python3
# -*- coding: utf-8 -*-
from argparse import ArgumentParser

import json
import os


def get_os_image(os_images, ocp_version, cpu_architecture="x86_64"):
    archs_images = [v for v in os_images if v.get('cpu_architecture') == cpu_architecture]
    os_images = [v for v in archs_images if v.get('openshift_version') == ocp_version]
    if len(os_images) >= 1:
        return os_images[0]

    return archs_images[-1]


def main():
    # Load default os images
    with open(args.src, 'r') as f:
        os_images: list = json.load(f)

    release_images = json.loads(os.getenv("RELEASE_IMAGES"))
    latest_ocp_version = release_images[-1]["openshift_version"]
    os_image = [v for v in os_images if v.get('openshift_version') == latest_ocp_version]

    # If OS image for latest OCP versions doesn't exists, clone latest OS image and override 'openshift_version'
    os_image = get_os_image(os_images, latest_ocp_version)
    if os_image["openshift_version"] != latest_ocp_version:
        new_image = os_image.copy()
        new_image["openshift_version"] = latest_ocp_version
        new_image["version"] = f"{os_image['openshift_version']}-assisted-override"
        os_images.append(new_image)

    json.dump(os_images, os.sys.stdout, separators=(',', ':'))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        '--src',
        type=str,
        help='OS images list file path'
    )
    args = parser.parse_args()
    main()
