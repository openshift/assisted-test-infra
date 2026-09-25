"""Collect install-debug evidence from libvirt VMs while they are still reachable.

Used when cluster install hangs (e.g. masters stuck joining the bootstrap control
plane). Console serial logs are often silent after GRUB; SSH as core@<ip> is the
reliable way to get kubelet/bootkube/keepalived journals before VMs are destroyed.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from paramiko import SSHException
from scp import SCPException

from assisted_test_infra.test_infra.controllers.node_controllers import Node
from assisted_test_infra.test_infra.helper_classes.nodes import Nodes
from assisted_test_infra.test_infra.tools import run_concurrently
from assisted_test_infra.test_infra.utils import utils
from service_client.logger import SuppressAndLog, log

# Units that typically explain control-plane join / VIP hangs.
_INSTALL_JOURNAL_UNITS = " ".join(
    [
        "bootkube",
        "kubelet",
        "crio",
        "keepalived",
        "release-image.service",
        "pivot",
        "agent",
        "ironic-agent",
        "progress.service",
        "node-valid-hostname",
    ]
)

# Use %%s-style substitution so bash ${OUT} braces are not interpreted by str.format.
_REMOTE_SCRIPT = r"""
set +e
OUT=/tmp/assisted_install_debug
rm -rf "${OUT}"
mkdir -p "${OUT}"
sudo journalctl -b --no-pager -u __UNITS__ -n 8000 > "${OUT}/journal_install_units.log" 2>&1
sudo journalctl -b --no-pager -n 25000 > "${OUT}/journal_boot.log" 2>&1
ip -br addr > "${OUT}/ip_addr.txt" 2>&1
ip route show > "${OUT}/ip_route.txt" 2>&1
ip -6 route show > "${OUT}/ip6_route.txt" 2>&1
sudo ss -lntp > "${OUT}/ss_listen.txt" 2>&1
sudo systemctl list-units --failed --no-pager > "${OUT}/failed_units.txt" 2>&1
sudo systemctl status bootkube kubelet crio keepalived --no-pager -l > "${OUT}/systemd_status.txt" 2>&1
command -v crictl >/dev/null && sudo crictl ps -a > "${OUT}/crictl_ps.txt" 2>&1
command -v podman >/dev/null && sudo podman ps -a > "${OUT}/podman_ps.txt" 2>&1
hostname > "${OUT}/hostname.txt" 2>&1
tar -C /tmp -czf /tmp/assisted_install_debug.tgz assisted_install_debug
chmod a+r /tmp/assisted_install_debug.tgz
""".replace("__UNITS__", _INSTALL_JOURNAL_UNITS)


def install_debug_destinations(test_name: str) -> List[Path]:
    """Return destinations under LOG_FOLDER and JUNIT_REPORT_DIR (CI gathers reports/)."""
    safe_name = test_name.replace("/", "_").replace("[", "_").replace("]", "_")
    destinations = [Path(os.environ.get("LOG_FOLDER", "/tmp/assisted_test_infra_logs")) / safe_name / "install_debug"]
    reports_dir = os.environ.get("JUNIT_REPORT_DIR")
    if reports_dir:
        destinations.append(Path(reports_dir) / "install_debug" / safe_name)
    else:
        destinations.append(Path("reports") / "install_debug" / safe_name)
    return destinations


def format_endpoint(ip: str, port: int) -> str:
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return f"{ip}:{port}"
    if parsed.version == 6:
        return f"[{ip}]:{port}"
    return f"{ip}:{port}"


def check_api_vip_connectivity(api_vips: Sequence[str], dest_dir: Path) -> None:
    """Best-effort VIP reachability from the provisioner (MCS 22623, kube-apiserver 6443)."""
    if not api_vips:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "api_vip_connectivity.txt"
    lines: List[str] = []
    for vip in api_vips:
        if not vip:
            continue
        for port in (6443, 22623):
            endpoint = format_endpoint(vip, port)
            cmd = (
                f"curl -k -sS -o /dev/null -w '%{{http_code}} %{{time_total}}s\\n' "
                f"--connect-timeout 5 --max-time 10 https://{endpoint}/ || echo failed"
            )
            lines.append(f"=== https://{endpoint}/ ===")
            try:
                stdout, stderr, rc = utils.run_command(cmd, shell=True, raise_errors=False)
                lines.append(f"rc={rc} stdout={stdout.strip()} stderr={stderr.strip()}")
            except Exception as exc:  # noqa: BLE001 - best effort diagnostics
                lines.append(f"error: {exc}")
    out_path.write_text("\n".join(lines) + "\n")
    log.info("Wrote API VIP connectivity probe to %s", out_path)


def _collect_from_node(node: Node, dest_dir: Path) -> None:
    node_dir = dest_dir / node.name
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "ips.txt").write_text("\n".join(node.ips or []) + "\n")
    remote_tgz = "/tmp/assisted_install_debug.tgz"
    local_tgz = node_dir / "assisted_install_debug.tgz"
    try:
        if not node.node_controller.is_active(node.name):
            (node_dir / "error.txt").write_text("node is not active\n")
            log.warning("Skipping install-debug for inactive node %s", node.name)
            return
        node.run_command(_REMOTE_SCRIPT)
        node.download_file(remote_tgz, str(local_tgz))
        utils.run_command(f"tar -xzf '{local_tgz}' -C '{node_dir}'", shell=True, raise_errors=False)
        log.info("Collected install-debug archive from %s (%s)", node.name, ",".join(node.ips or []))
    except (RuntimeError, TimeoutError, SSHException, SCPException) as exc:
        (node_dir / "error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
        log.warning("Could not collect install-debug from %s: %s", node.name, exc)


def collect_nodes_install_debug(
    nodes: Nodes,
    dest_dirs: Iterable[Path],
    api_vips: Optional[Sequence[str]] = None,
) -> None:
    """SSH to each VM as core and gather journals useful for install hang triage."""
    dest_list = [Path(d) for d in dest_dirs]
    if not dest_list:
        return

    primary = dest_list[0]
    primary.mkdir(parents=True, exist_ok=True)
    log.info("Collecting install-debug logs into %s", primary)

    with SuppressAndLog(Exception):
        check_api_vip_connectivity(api_vips or [], primary)

    node_list = list(nodes.get_nodes(refresh=True))
    if not node_list:
        log.warning("No nodes available for install-debug collection")
        return

    run_concurrently(jobs=[(_collect_from_node, node, primary) for node in node_list], timeout=60 * 15)

    # Mirror into extra destinations (e.g. reports/ for CI gather).
    for extra in dest_list[1:]:
        if extra.resolve() == primary.resolve():
            continue
        extra.parent.mkdir(parents=True, exist_ok=True)
        utils.run_command(f"rm -rf '{extra}' && cp -a '{primary}' '{extra}'", shell=True, raise_errors=False)
        log.info("Mirrored install-debug logs to %s", extra)
