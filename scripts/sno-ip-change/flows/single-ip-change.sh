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

OLD_IP=""
NEW_IP=""
NEW_MACHINE_NETWORK=""
NEW_GATEWAY_IP=""
NEW_DNS_SERVER=""
RECERT_IMAGE_TAR=""
REMOTE_NODE_ACTIONS_FILENAME="single-node-actions.sh"

# SSH parameters
SSH_HOST=""
SSH_USER="core"
SSH_PORT="22"
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_STRICT_HOSTKEY_CHECKING="no"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ip) OLD_IP="$2"; shift 2;;
    --new-ip) NEW_IP="$2"; shift 2;;
    --new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
    --new-gateway-ip) NEW_GATEWAY_IP="$2"; shift 2;;
    --new-dns-server) NEW_DNS_SERVER="$2"; shift 2;;
    --recert-image-tar) RECERT_IMAGE_TAR="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --ssh-strict-hostkey-checking) SSH_STRICT_HOSTKEY_CHECKING="$2"; shift 2;;
    *) fail "Unknown argument: $1";;
  esac
done

main() {
  need_cmd ssh
  need_cmd scp

  [[ -n "$OLD_IP" ]] || fail "--old-ip is required"
  [[ -n "$NEW_IP" ]] || fail "--new-ip is required"
  [[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required (CIDR like a.b.c.0/24 or v6)"
  [[ -n "$NEW_GATEWAY_IP" ]] || fail "--new-gateway-ip is required"
  [[ -n "$RECERT_IMAGE_TAR" && -f "$RECERT_IMAGE_TAR" ]] || fail "--recert-image-tar is required and must exist"

  if [[ "$OLD_IP" == "$NEW_IP" ]]; then
    log "Old and new IP are identical (${OLD_IP}); nothing to do."
    exit 0
  fi

  SSH_HOST="$OLD_IP"

  # Stage remote working directory and files
  local remote_dir
  remote_dir=$(prepare_remote_dir "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING")
  log "Prepared remote working directory: ${remote_dir}"

  # Copy required libs and remote runner script
  copy_dir_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/lib" "${remote_dir}/lib"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/remote/${REMOTE_NODE_ACTIONS_FILENAME}" "${remote_dir}/${REMOTE_NODE_ACTIONS_FILENAME}"

  # Copy provided recert image archive to the node so it can be loaded locally
  local recert_archive_remote_path
  local remote_path
  remote_path="${remote_dir}/recert-image.tar"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$RECERT_IMAGE_TAR" "$remote_path"
  recert_archive_remote_path="$remote_path"

  # Execute remote actions as root
  local remote_cmd
  remote_cmd=("sudo" "bash" "${remote_dir}/${REMOTE_NODE_ACTIONS_FILENAME}"
    "--old-ip" "$OLD_IP"
    "--new-ip" "$NEW_IP"
    "--new-machine-network" "$NEW_MACHINE_NETWORK"
    "--new-gateway-ip" "$NEW_GATEWAY_IP"
    "--recert-image-archive" "${recert_archive_remote_path}"
  )
  if [[ -n "$NEW_DNS_SERVER" ]]; then
    remote_cmd+=("--new-dns-server" "$NEW_DNS_SERVER")
  fi
  ssh_exec "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${remote_cmd[@]}"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
