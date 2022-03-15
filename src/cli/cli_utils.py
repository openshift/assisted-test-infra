import functools
import json
import subprocess
from typing import List

from tests.global_variables.default_variables import DefaultVariables

__global_variables = DefaultVariables()


def get_namespace() -> List[str]:
    res = subprocess.check_output(["kubectl", "get", "ns", "--output=json"])
    try:
        namespaces = json.loads(res)
    except json.JSONDecodeError:
        return []

    return [ns["metadata"]["name"] for ns in namespaces["items"]]


@functools.cache
def get_boolean_keys():
    bool_env_vars = [
        __global_variables.get_env(k).var_keys
        for k in __global_variables.__dataclass_fields__
        if isinstance(getattr(__global_variables, k), bool)
    ]
    return [item for sublist in bool_env_vars for item in sublist]


@functools.cache
def get_env_args_keys():
    env_vars = [__global_variables.get_env(k).var_keys for k in __global_variables.__dataclass_fields__]
    return [item for sublist in env_vars for item in sublist]


@functools.cache
def inventory_client():
    return __global_variables.get_api_client()
