import json
import re
from importlib import metadata
from subprocess import PIPE, CalledProcessError, check_output

from consts import consts
from service_client.logger import log
from tests.global_variables import DefaultVariables

global_variables = DefaultVariables()


def _get_service_container(namespace: str):
    res = check_output(["kubectl", "get", "pods", "-n", namespace, "--output=json"])
    data = json.loads(res)
    containers = [item["metadata"]["name"] for item in data["items"] if item and item["metadata"]]
    service_containers = [container for container in containers if container.startswith("assisted-service")]

    return service_containers[0] if service_containers else ""


def _get_service_version(service_container_name: str, namespace: str) -> str:
    try:
        cmd = f"kubectl exec -it --namespace={namespace} {service_container_name} -- bash -c 'ls /clients/*.tar.gz'"
        src_client_file = check_output(cmd, shell=True, stderr=PIPE)
        version = re.findall(r"assisted-service-client-(.*).tar.gz", src_client_file.decode())[0]
        return version.strip()
    except (CalledProcessError, KeyError):
        return ""


def verify_client_version(namespace="assisted-installer"):
    """Check if the client artifact that exists on the service instance equal to the installed client version
    on test-infra image"""

    if global_variables.deploy_target == consts.DeployTargets.ONPREM:
        log.info("Onprem environment assisted-python-client validation is currently not supported")
        return

    try:
        service = _get_service_container(namespace)
        service_version = _get_service_version(service, namespace)
        client_installed_version = metadata.version("assisted-service-client")
        if service_version == client_installed_version:
            log.info(
                f"Assisted python client versions match! Version on {service}={service_version} == "
                f"installed_version={client_installed_version}"
            )
        else:
            log.warning(
                f"Mismatch client versions found! Version on {service}={service_version} != "
                f"installed_version={client_installed_version}"
            )

    except BaseException as e:
        # best effort
        log.info(f"Failed to validate assisted-python-client version, {e}")


if __name__ == "__main__":
    verify_client_version()
