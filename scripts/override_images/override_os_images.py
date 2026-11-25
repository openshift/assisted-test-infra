#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overrides a given list of OS images to the OS images that match the
release image in RELEASE_IMAGES (same OpenShift version and CPU architecture).
"""

# Disable E402 module level import not at top of file
# triggered because of the logging import that should be on top
# flake8: noqa: E402

# disable all logging to not mess up with the output of this script
import logging

logging.disable(logging.CRITICAL)

import json
import os
import sys

from assisted_service_client.models import OsImage, ReleaseImage

from consts import DEFAULT_CPU_ARCHITECTURE, CPUArchitecture


def get_os_image(
    os_images: list[OsImage], openshift_version: str, cpu_architecture: str = DEFAULT_CPU_ARCHITECTURE
) -> list[OsImage]:
    return [
        v
        for v in os_images
        if v.cpu_architecture == cpu_architecture and v.openshift_version == openshift_version
    ]


def main():
    if (os_images_path := os.getenv("OS_IMAGES_PATH", "")) == "":
        raise ValueError("OS_IMAGES_PATH environment variable must be provided")

    # Load default os images
    with open(os_images_path, "r") as f:
        os_images = [OsImage(**os_image_dict) for os_image_dict in json.load(f)]

    if (release_images := os.getenv("RELEASE_IMAGES", "")) == "":
        raise ValueError("RELEASE_IMAGES environment variable must be provided")

    try:
        release_images = [ReleaseImage(**release_image_dict) for release_image_dict in json.loads(release_images)]
    except json.JSONDecodeError as e:
        raise ValueError("RELEASE_IMAGES enironment variable content is invalid JSON") from e

    if len(release_images) != 1:
        raise ValueError(
            "RELEASE_IMAGES enironment variable content must contain exactly one release image after its override"
        )

    release_image = release_images[0]
    filtered_os_images: list[OsImage] = []

    # Get all matching OS images
    if release_image.cpu_architecture == CPUArchitecture.MULTI:
        for arch in {CPUArchitecture.X86, CPUArchitecture.ARM, CPUArchitecture.S390X, CPUArchitecture.PPC64}:
            filtered_os_images.extend(
                get_os_image(
                    os_images=os_images,
                    openshift_version=str(release_image.openshift_version).removesuffix(f"-{CPUArchitecture.MULTI}"),
                    cpu_architecture=arch,
                )
            )

    else:
        matching_os_images = get_os_image(
            os_images=os_images,
            openshift_version=str(release_image.openshift_version),
            cpu_architecture=str(release_image.cpu_architecture),
        )
        if not matching_os_images:
            raise ValueError(
                "Failed find get OS image matching openshift_version:"
                f"{release_image.openshift_version} and CPU architecture: {release_image.cpu_architecture}"
            )
        filtered_os_images.extend(matching_os_images)

    if not filtered_os_images:
        raise ValueError("No OS Images found")

    os_images = [os_image.to_dict() for os_image in filtered_os_images]
    json.dump(os_images, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
