#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Idea is to pass os environments to assisted-service config map, to make an easy way to configure assisted-service
#
# Note: defaulting an env var to "" in Makefile, will result in an empty string value in the configmap.
# E.g.
# Makefile:
#   MY_VAR := $(or $(MY_VAR), "")
# configmap:
#   MY_VAR: ""
#
# Hence, in order to support unset env vars, avoid override in Makefile.

import os

import yaml

CM_PATH = "assisted-service/deploy/assisted-service-configmap.yaml"
ENVS = [
    ("HW_VALIDATOR_MIN_CPU_CORES", "2"),
    ("HW_VALIDATOR_MIN_CPU_CORES_WORKER", "2"),
    ("HW_VALIDATOR_MIN_CPU_CORES_MASTER", "4"),
    ("HW_VALIDATOR_MIN_RAM_GIB", "3"),
    ("HW_VALIDATOR_MIN_RAM_GIB_WORKER", "3"),
    ("HW_VALIDATOR_MIN_RAM_GIB_MASTER", "8"),
    ("HW_VALIDATOR_MIN_DISK_SIZE_GIB", "10"),
    ("INSTALLER_IMAGE", ""),
    ("CONTROLLER_IMAGE", ""),
    ("SERVICE_BASE_URL", ""),
    ("AGENT_DOCKER_IMAGE", ""),
    ("IGNITION_GENERATE_IMAGE", ""),
    ("BASE_DNS_DOMAINS", ""),
    ("IMAGE_BUILDER", ""),
    ("CONNECTIVITY_CHECK_IMAGE", ""),
    ("HARDWARE_INFO_IMAGE", ""),
    ("INVENTORY_IMAGE", ""),
    ("OCM_BASE_URL", ""),
    ("PUBLIC_CONTAINER_REGISTRIES", "")
]


def _read_yaml():
    if not os.path.exists(CM_PATH):
        return
    with open(CM_PATH, "r+") as cm_file:
        return yaml.load(cm_file)


def _get_relevant_envs():
    data = {}
    for env in ENVS:
        evn_data = os.getenv(env[0], env[1])
        # Set value as empty if variable is an empty string (e.g. defaulted in Makefile)
        if evn_data == '""':
            data[env[0]] = ""
        elif evn_data:
            data[env[0]] = evn_data
    return data


def set_envs_to_service_cm():
    cm_data = _read_yaml()
    if not cm_data:
        raise Exception("%s must exists before setting envs to it" % CM_PATH)
    cm_data["data"].update(_get_relevant_envs())
    with open(CM_PATH, "w") as cm_file:
        yaml.dump(cm_data, cm_file)


if __name__ == "__main__":
    set_envs_to_service_cm()
