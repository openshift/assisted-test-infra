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
import json
import os
import yaml

from deprecated_utils import warn_deprecate

warn_deprecate()


CM_PATH = "assisted-service/deploy/assisted-service-configmap.yaml"
ENVS = [
    ("INSTALLER_IMAGE", ""),
    ("CONTROLLER_IMAGE", ""),
    ("SERVICE_BASE_URL", ""),
    ("IMAGE_SERVICE_BASE_URL", ""),
    ("AGENT_DOCKER_IMAGE", ""),
    ("BASE_DNS_DOMAINS", ""),
    ("IMAGE_BUILDER", ""),
    ("OCM_BASE_URL", ""),
    ("AGENT_TIMEOUT_START", ""),
    ("PUBLIC_CONTAINER_REGISTRIES", ""),
    ("CHECK_CLUSTER_VERSION", ""),
    ("HW_VALIDATOR_REQUIREMENTS", ""),
    ("HW_VALIDATOR_MIN_CPU_CORES_SNO", ""),
    ("HW_VALIDATOR_MIN_RAM_GIB_SNO", "")
]
DEFAULT_MASTER_REQUIREMENTS = {
    "cpu_cores": 4,
    "ram_mib": 8192,
    "disk_size_gb": 10,
    "installation_disk_speed_threshold_ms": 10
}
DEFAULT_WORKER_REQUIREMENTS = {
    "cpu_cores": 2,
    "ram_mib": 3072,
    "disk_size_gb": 10,
    "installation_disk_speed_threshold_ms": 10
}
DEFAULT_SNO_REQUIREMENTS = {
    "cpu_cores": 8,
    "ram_mib": 32768,
    "disk_size_gb": 10,
    "installation_disk_speed_threshold_ms": 10
}
DEFAULT_REQUIREMENTS = [{
    "version": "default",
    "master": DEFAULT_MASTER_REQUIREMENTS,
    "worker": DEFAULT_WORKER_REQUIREMENTS,
    "sno": DEFAULT_SNO_REQUIREMENTS
}]


def _read_yaml():
    if not os.path.exists(CM_PATH):
        return
    with open(CM_PATH, "r+") as cm_file:
        return yaml.safe_load(cm_file)


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


def update_requirements(requirements_json):
    if requirements_json == "" or requirements_json == "REPLACE_HW_VALIDATOR_REQUIREMENTS":
        return json.dumps(DEFAULT_REQUIREMENTS)
    requirements = json.loads(requirements_json)
    for version_requirements in requirements:
        if version_requirements["version"] == "default":
            version_requirements["master"] = DEFAULT_MASTER_REQUIREMENTS
            version_requirements["worker"] = DEFAULT_WORKER_REQUIREMENTS
            version_requirements["sno"] = DEFAULT_SNO_REQUIREMENTS

    return json.dumps(requirements)


def set_envs_to_service_cm():
    cm_data = _read_yaml()
    if not cm_data:
        raise Exception("%s must exists before setting envs to it" % CM_PATH)
    cm_data["data"].update(_get_relevant_envs())
    existing_requirements = cm_data["data"].get("HW_VALIDATOR_REQUIREMENTS", "")
    requirements = update_requirements(existing_requirements)
    cm_data["data"].update({"HW_VALIDATOR_REQUIREMENTS": requirements})
    with open(CM_PATH, "w") as cm_file:
        yaml.dump(cm_data, cm_file)


if __name__ == "__main__":
    set_envs_to_service_cm()
