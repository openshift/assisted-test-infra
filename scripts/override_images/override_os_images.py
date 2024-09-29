#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overrides a given list of OS images to a list with a single OS image
that matches the latest release image in RELEASE_IMAGES
"""
import json
import os
import sys

import semver
from assisted_service_client.models import OsImage, ReleaseImage

from consts import DEFAULT_CPU_ARCHITECTURE


def get_os_image(
    os_images: list[OsImage], openshift_version: str, cpu_architecture: str = DEFAULT_CPU_ARCHITECTURE
) -> OsImage | None:
    archs_images = [v for v in os_images if v.cpu_architecture == cpu_architecture]
    os_images = [v for v in archs_images if v.openshift_version == openshift_version]
    if len(os_images) >= 1:
        return os_images[0]

    return None


def main():
    if (os_images_path := os.getenv("OS_IMAGES_PATH", "")) == "":
        raise ValueError("OS_IMAGES_PATH environment variable must be provided")

    # Load default os images
    with open(os_images_path, "r") as f:
        os_images = [OsImage(**os_image_dict) for os_image_dict in json.load(f)]

    if (release_images := os.getenv("RELEASE_IMAGES", "")) == "":
        raise ValueError("RELEASE_IMAGES environment variable must be provided")

    try:
        release_images = json.loads(release_images)
    except json.JSONDecodeError as e:
        raise ValueError("RELEASE_IMAGES enironment variable content is invalid JSON") from e

    if len(release_images) == 0:
        raise ValueError("RELEASE_IMAGES enironment variable content must contain at least one release")

    # get latest default CPU architecture release image
    release_image_objects = [
        ReleaseImage(**release_image)
        for release_image in release_images
        if release_image["cpu_architecture"] == DEFAULT_CPU_ARCHITECTURE
    ]
    release_images_map = {
        semver.VersionInfo.parse(
            release_image.version.removesuffix("-multi"), optional_minor_and_patch=True
        ): release_image
        for release_image in release_image_objects
    }
    latest_release_image_version = sorted(release_images_map.keys(), key=lambda version: version)[-1]
    latest_release_image = release_images_map[latest_release_image_version]

    if (
        os_image := get_os_image(os_images=os_images, openshift_version=str(latest_release_image.openshift_version))
    ) is None:
        raise ValueError(
            f"""no OS image found with openshift_version:
            {latest_release_image.openshift_version} for the latest release image
            """
        )

    os_images_dict = [os_image.to_dict()]

    json.dump(os_images_dict, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
