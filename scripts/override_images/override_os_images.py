#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overrides a given list of OS images to a list with a single OS image
that matches the latest release image in RELEASE_IMAGES
"""
import json
import os
import sys

from assisted_service_client.models import OsImage, ReleaseImage

from consts import DEFAULT_CPU_ARCHITECTURE, CPUArchitecture


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
            if (
                os_image := get_os_image(
                    os_images=os_images,
                    openshift_version=str(release_image.openshift_version).removesuffix(f"-{CPUArchitecture.MULTI}"),
                    cpu_architecture=arch,
                )
            ) is not None:
                filtered_os_images.append(os_image)

    else:
        if (
            os_image := get_os_image(
                os_images=os_images,
                openshift_version=str(release_image.openshift_version),
                cpu_architecture=str(release_image.cpu_architecture),
            )
        ) is None:
            raise ValueError(
                "Failed find get OS image matching openshift_version:"
                f"{release_image.openshift_version} and CPU architecture: {release_image.cpu_architecture}"
            )
        filtered_os_images.append(os_image)

    if filtered_os_images == 0:
        raise ValueError("No OS Images found")

    os_images = [os_image.to_dict() for os_image in filtered_os_images]
    json.dump(os_images, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
