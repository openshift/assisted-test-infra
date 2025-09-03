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

OLD_IPV4=""
NEW_IPV4=""
NEW_MACHINE_NETWORK_V4=""
OLD_IPV6=""
NEW_IPV6=""
NEW_MACHINE_NETWORK_V6=""
PRIMARY_STACK="v4"
SSH_USER="core"
SSH_PORT="22"
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_STRICT_HOSTKEY_CHECKING="no"
RECERT_IMAGE_TAR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ipv4) OLD_IPV4="$2"; shift 2;;
    --new-ipv4) NEW_IPV4="$2"; shift 2;;
    --new-machine-network-v4) NEW_MACHINE_NETWORK_V4="$2"; shift 2;;
    --old-ipv6) OLD_IPV6="$2"; shift 2;;
    --new-ipv6) NEW_IPV6="$2"; shift 2;;
    --new-machine-network-v6) NEW_MACHINE_NETWORK_V6="$2"; shift 2;;
    --primary-stack) PRIMARY_STACK="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --ssh-strict-hostkey-checking) SSH_STRICT_HOSTKEY_CHECKING="$2"; shift 2;;
    --recert-image-tar) RECERT_IMAGE_TAR="$2"; shift 2;;
    *) fail "Unknown argument: $1";;
  esac
done

main() {
  need_cmd ssh
  need_cmd scp

  [[ -n "$OLD_IPV4" ]] || fail "--old-ipv4 is required"
  [[ -n "$NEW_IPV4" ]] || fail "--new-ipv4 is required"
  [[ -n "$NEW_MACHINE_NETWORK_V4" ]] || fail "--new-machine-network-v4 is required (CIDR)"
  [[ -n "$OLD_IPV6" ]] || fail "--old-ipv6 is required"
  [[ -n "$NEW_IPV6" ]] || fail "--new-ipv6 is required"
  [[ -n "$NEW_MACHINE_NETWORK_V6" ]] || fail "--new-machine-network-v6 is required (CIDR)"
  [[ "$PRIMARY_STACK" == "v4" || "$PRIMARY_STACK" == "v6" ]] || fail "--primary-stack must be 'v4' or 'v6'"
  [[ -n "$RECERT_IMAGE_TAR" && -f "$RECERT_IMAGE_TAR" ]] || fail "--recert-image-tar is required and must exist"

  if [[ "$OLD_IPV4" == "$NEW_IPV4" && "$OLD_IPV6" == "$NEW_IPV6" ]]; then
    log "Old and new IPv4/IPv6 are identical. Nothing to change."
    exit 0
  fi

  local SSH_HOST
  if [[ "$PRIMARY_STACK" == "v4" ]]; then
    SSH_HOST="$OLD_IPV4"
  else
    SSH_HOST="$OLD_IPV6"
  fi

  log "Preparing remote working directory on node ${SSH_HOST}"
  local remote_dir
  remote_dir=$(prepare_remote_dir "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING")
  log "Remote working directory: ${remote_dir}"

  copy_dir_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/lib" "${remote_dir}/lib"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/remote/dual-node-actions.sh" "${remote_dir}/node-actions.sh"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$RECERT_IMAGE_TAR" "${remote_dir}/recert-image.tar"

  local remote_cmd
  remote_cmd=("sudo" "bash" "${remote_dir}/node-actions.sh"
    "--old-ipv4" "$OLD_IPV4"
    "--new-ipv4" "$NEW_IPV4"
    "--new-machine-network-v4" "$NEW_MACHINE_NETWORK_V4"
    "--old-ipv6" "$OLD_IPV6"
    "--new-ipv6" "$NEW_IPV6"
    "--new-machine-network-v6" "$NEW_MACHINE_NETWORK_V6"
    "--primary-stack" "$PRIMARY_STACK"
    "--recert-image-archive" "${remote_dir}/recert-image.tar"
  )
  ssh_exec "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${remote_cmd[@]}"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi



