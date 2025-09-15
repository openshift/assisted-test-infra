#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC1091

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/util.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/util.sh"
# shellcheck source=lib/ssh.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/ssh.sh"
# shellcheck source=lib/network.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/network.sh"

# Defaults
OLD_IP=""
NEW_IP=""
NEW_MACHINE_NETWORK=""
NEW_GATEWAY_IP=""
NEW_DNS_SERVER=""
SSH_USER="core"
SSH_PORT="22"
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_STRICT_HOSTKEY_CHECKING="no"

# Internal kubeconfig path used on the node
KUBECONFIG_INTERNAL_PATH="/etc/kubernetes/static-pod-resources/kube-apiserver-certs/secrets/node-kubeconfigs/lb-ext.kubeconfig"

usage() {
  cat <<USAGE
Usage: $0 --old-ip <ip> --new-ip <ip> --new-machine-network <cidr> --new-gateway-ip <gateway> [--new-dns-server <dns>] [--ssh-user core] [--ssh-port 22] [--ssh-key ~/.ssh/id_rsa] [--ssh-strict-hostkey-checking no]

Description:
  Applies a MachineConfig on a dual-stack SNO node to change its secondary IP,
  then reboots the node, waits for SSH on the new IP, and reboots again.

Required:
  --old-ip    Existing (pre-change) IP address to connect to initially
  --new-ip    New IP address to wait for and connect to after first reboot
  --new-machine-network  CIDR for the network of the new IP (e.g. 192.168.201.0/24 or fd00::/64)
  --new-gateway-ip  Gateway IP address for the new network

Optional:
  --new-dns-server  DNS server IP address for the new network

Optional SSH params:
  --ssh-user
  --ssh-port
  --ssh-key
  --ssh-strict-hostkey-checking  (yes|no)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ip) OLD_IP="$2"; shift 2;;
    --new-ip) NEW_IP="$2"; shift 2;;
    --new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
    --new-gateway-ip) NEW_GATEWAY_IP="$2"; shift 2;;
    --new-dns-server) NEW_DNS_SERVER="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --ssh-strict-hostkey-checking) SSH_STRICT_HOSTKEY_CHECKING="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) fail "Unknown argument: $1";;
  esac
done

main() {
  need_cmd ssh
  need_cmd scp

  [[ -n "$OLD_IP" ]] || { usage; fail "--old-ip is required"; }
  [[ -n "$NEW_IP" ]] || { usage; fail "--new-ip is required"; }
  [[ -n "$NEW_MACHINE_NETWORK" ]] || { usage; fail "--new-machine-network is required"; }
  [[ -n "$NEW_GATEWAY_IP" ]] || { usage; fail "--new-gateway-ip is required"; }

  # Ensure initial SSH connectivity to old IP
  log "Ensuring SSH connectivity to ${OLD_IP}"
  ssh_wait "$SSH_USER" "$OLD_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" 300 || true

  log "Preparing remote working directory on node ${OLD_IP}"
  local remote_dir
  remote_dir=$(prepare_remote_dir "$SSH_USER" "$OLD_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING")
  log "Remote working directory: ${remote_dir}"

  copy_dir_to_remote "$SSH_USER" "$OLD_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/lib" "${remote_dir}/lib"
  copy_to_remote "$SSH_USER" "$OLD_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/remote/secondary-node-actions.sh" "${remote_dir}/secondary-node-actions.sh"

  log "Running remote node actions"
  local remote_cmd
  remote_cmd=("sudo" "bash" "${remote_dir}/secondary-node-actions.sh" "--new-ip" "$NEW_IP" "--new-machine-network" "$NEW_MACHINE_NETWORK" "--new-gateway-ip" "$NEW_GATEWAY_IP")
  if [[ -n "$NEW_DNS_SERVER" ]]; then
    remote_cmd+=("--new-dns-server" "$NEW_DNS_SERVER")
  fi
  ssh_exec "$SSH_USER" "$OLD_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${remote_cmd[@]}" || true

  log "Waiting for SSH on new IP ${NEW_IP}"
  ssh_wait "$SSH_USER" "$NEW_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" 1200

  log "Initiating second reboot on new IP ${NEW_IP}"
  ssh_exec "$SSH_USER" "$NEW_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" sudo systemctl reboot || true

  log "Waiting for SSH to come back on new IP ${NEW_IP}"
  ssh_wait "$SSH_USER" "$NEW_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" 1200
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi


