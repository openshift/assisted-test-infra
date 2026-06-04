"""
Kube-API / operator hub: apply openshift-install image policy override via kubectl.

1. ConfigMap ``assisted-installer-config-override`` in ``NAMESPACE`` (LOG_LEVEL + policy key).
2. Merge-patch cluster ``AgentServiceConfig`` (no ``-n`` — cluster-scoped) to reference that ConfigMap.

The operator merges the overlay ConfigMap into assisted-service config; we do not patch
``assisted-service-config`` directly (non-operator / kind uses ``update_assisted_service_cm.py``).

Environment (optional): ``NAMESPACE``, ``KUBECONFIG``,
``ASSISTED_INSTALLER_CONFIG_OVERRIDE_ASC_NAME`` (default ``agent``),
``ASSISTED_INSTALLER_CONFIG_OVERRIDE_CM_NAME`` (default ``assisted-installer-config-override``).

On failure: log and exit non-zero.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional

ENV_KEY = "OPENSHIFT_INSTALL_EXPERIMENTAL_DISABLE_IMAGE_POLICY"
ANNOTATION_KEY = "unsupported.agent-install.openshift.io/assisted-service-configmap"


def _kubectl_prefix(kubeconfig_path: Optional[str]) -> list[str]:
    cmd = ["kubectl"]
    if kubeconfig_path:
        cmd.extend(["--kubeconfig", kubeconfig_path])
    return cmd


def _run(cmd: list[str], stdin: Optional[bytes] = None) -> None:
    subprocess.run(cmd, input=stdin, check=True, capture_output=True)


def apply_assisted_installer_config_override(
    kubeconfig_path: Optional[str] = None,
    namespace: Optional[str] = None,
    asc_name: Optional[str] = None,
    override_cm_name: Optional[str] = None,
) -> None:
    namespace = namespace or os.environ.get("NAMESPACE", "assisted-installer")
    asc_name = asc_name or os.environ.get("ASSISTED_INSTALLER_CONFIG_OVERRIDE_ASC_NAME", "agent")
    override_cm_name = override_cm_name or os.environ.get(
        "ASSISTED_INSTALLER_CONFIG_OVERRIDE_CM_NAME", "assisted-installer-config-override"
    )
    kubeconfig_path = kubeconfig_path if kubeconfig_path is not None else os.environ.get("KUBECONFIG")

    prefix = _kubectl_prefix(kubeconfig_path)

    cm_yaml = (
        "apiVersion: v1\n"
        "kind: ConfigMap\n"
        "metadata:\n"
        f"  name: {override_cm_name}\n"
        f"  namespace: {namespace}\n"
        "data:\n"
        '  LOG_LEVEL: "debug"\n'
        f'  {ENV_KEY}: "true"\n'
    )

    asc_patch = json.dumps({"metadata": {"annotations": {ANNOTATION_KEY: override_cm_name}}})

    try:
        _run([*prefix, "apply", "-f", "-"], stdin=cm_yaml.encode("utf-8"))
        _run(
            [
                *prefix,
                "patch",
                f"agentserviceconfig/{asc_name}",
                "--type=merge",
                "-p",
                asc_patch,
            ]
        )
    except FileNotFoundError:
        print("assisted_installer_config_override: kubectl not found", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        print(f"assisted_installer_config_override: kubectl failed ({e.returncode}): {err}", file=sys.stderr)
        raise


def main() -> None:
    try:
        apply_assisted_installer_config_override()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
