#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overrides the list of release images according to
OPENSHIFT_VERSION or OPENSHIFT_INSTALL_RELEASE_IMAGE environment variables.
Should result in single release image.
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

import semver
from assisted_service_client.models import ReleaseImage

from assisted_test_infra.test_infra import utils
from consts import DEFAULT_CPU_ARCHITECTURE, CPUArchitecture


def get_release_image(
    release_images: list[ReleaseImage], ocp_xy_version: str, cpu_architecture: str = DEFAULT_CPU_ARCHITECTURE
) -> ReleaseImage | None:
    archs_images = [v for v in release_images if v.cpu_architecture == cpu_architecture]
    release_image = [v for v in archs_images if v.openshift_version == ocp_xy_version]
    if len(release_image) >= 1:
        return release_image[0]

    return None


def main():
    if (release_images_path := os.getenv("RELEASE_IMAGES_PATH", "")) == "":
        raise ValueError("RELEASE_IMAGES_PATH environment variable must be provided")

    # Load default release images
    with open(release_images_path, "r") as f:
        release_images = [ReleaseImage(**release_image_dict) for release_image_dict in json.load(f)]

    if (version := os.getenv("OPENSHIFT_VERSION", "")) != "":
        try:
            sem_version = semver.VersionInfo.parse(version, optional_minor_and_patch=True)
        except ValueError as e:
            raise ValueError("provided OPENSHIFT_VERSION is not a valid semantic version") from e

        suffix = f"-{CPUArchitecture.MULTI}" if version.endswith(f"-{CPUArchitecture.MULTI}") else ""
        ocp_xy_version = f"{sem_version.major}.{sem_version.minor}{suffix}"
        cpu_architecture = CPUArchitecture.MULTI if CPUArchitecture.MULTI in suffix else DEFAULT_CPU_ARCHITECTURE

        if (
            release_image := get_release_image(
                release_images=release_images, ocp_xy_version=ocp_xy_version, cpu_architecture=cpu_architecture
            )
        ) is None:
            raise ValueError(
                f"""
                No release image found with 'openshift_version':
                {ocp_xy_version} and cpu_architecture: {cpu_architecture}"
            """
            )

        release_image.default = True

    elif (release_image_ref := os.getenv("OPENSHIFT_INSTALL_RELEASE_IMAGE", "")) != "":
        ocp_semantic_version = utils.extract_version(release_image=release_image_ref)
        cpu_architecture = utils.extract_architecture(release_image=release_image_ref)
        cpu_architectures = (
            [CPUArchitecture.X86, CPUArchitecture.ARM, CPUArchitecture.S390X, CPUArchitecture.PPC64]
            if cpu_architecture == CPUArchitecture.MULTI
            else [cpu_architecture]
        )
        suffix = CPUArchitecture.MULTI if cpu_architecture == CPUArchitecture.MULTI else ""
        ocp_xy_version = f"{ocp_semantic_version.major}.{ocp_semantic_version.minor}{suffix}"

        release_image = ReleaseImage(
            openshift_version=ocp_xy_version,
            version=str(ocp_semantic_version),
            cpu_architecture=cpu_architecture,
            cpu_architectures=cpu_architectures,
            default=True,
            url=release_image_ref,
        )

    else:
        raise ValueError(
            "OPENSHIFT_INSTALL_RELEASE_IMAGE or OPENSHIFT_VERSION must be specified in order to override RELEASE_IMAGES"
        )

    release_images = [release_image.to_dict()]
    json.dump(release_images, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
