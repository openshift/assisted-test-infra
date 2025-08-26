#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC1091

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/util.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/util.sh"
# shellcheck source=lib/network.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/network.sh"
# shellcheck source=lib/mc.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/mc.sh"
# shellcheck source=lib/recert.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/recert.sh"
# shellcheck source=lib/dns.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/dns.sh"
# shellcheck source=lib/crypto.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/crypto.sh"
# shellcheck source=lib/cluster.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/cluster.sh"
# shellcheck source=lib/ssh.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/ssh.sh"

OLD_IP=""
NEW_IP=""
NEW_MACHINE_NETWORK=""
PULL_SECRET_PATH=""
INSTALL_CONFIG_PATH="$(mktemp)"
RECERT_IMAGE="quay.io/dmanor/recert:demo"
RECERT_CONTAINER_DATA_DIR_PATH="/data"
PRIMARY_IP_PATH="/run/nodeip-configuration/primary-ip"
NODEIP_DEFAULTS_PATH="/etc/default/nodeip-configuration"
NODEIP_RERUN_UNIT_PATH="/etc/systemd/system/sno-nodeip-rerun.service"
REMOTE_NODE_ACTIONS_FILENAME="node-actions.sh"
REMOTE_INSTALL_CONFIG_FILENAME="install_config_block.yaml"
REMOTE_PULL_SECRET_FILENAME="pull-secret.json"
REMOTE_RECERT_DIR_NAME="recert-crypto"
REMOTE_RECERT_JSON_NAME="recert-crypto.json"
SSH_WAIT_TIMEOUT_SECS="1200"
CONTEXT_MSG_NMSTATE_MC="nmstate MC"
NMSTATE_FILE_PATH=""

# External (local) kubeconfig path
KUBECONFIG_EXTERNAL_PATH=""

# SSH parameters
SSH_HOST=""
SSH_USER="core"
SSH_PORT="22"
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_STRICT_HOSTKEY_CHECKING="no"

# Optional: none; mirroring handled automatically for IPv6

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ip) OLD_IP="$2"; shift 2;;
    --new-ip) NEW_IP="$2"; shift 2;;
    --new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
    --pull-secret-path) PULL_SECRET_PATH="$2"; shift 2;;
    --recert-image) RECERT_IMAGE="$2"; shift 2;;
    --kubeconfig-path) KUBECONFIG_EXTERNAL_PATH="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --ssh-strict-hostkey-checking) SSH_STRICT_HOSTKEY_CHECKING="$2"; shift 2;;
    *) fail "Unknown argument: $1";;
  esac
done

main() {
  need_cmd sed
  need_cmd jq
  need_cmd oc
  need_cmd ssh
  need_cmd scp
  need_cmd base64
  need_cmd podman

  [[ -n "$OLD_IP" ]] || fail "--old-ip is required"
  [[ -n "$NEW_IP" ]] || fail "--new-ip is required"
  [[ -n "$PULL_SECRET_PATH" ]] || fail "--pull-secret is required"
  [[ -f "$PULL_SECRET_PATH" ]] || fail "Pull secret file not found: $PULL_SECRET_PATH"
  [[ -n "$KUBECONFIG_EXTERNAL_PATH" ]] || fail "--kubeconfig-path is required"
  [[ -f "$KUBECONFIG_EXTERNAL_PATH" ]] || fail "kubeconfig not found: $KUBECONFIG_EXTERNAL_PATH"
  [[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required (CIDR like a.b.c.0/24 or v6)"

  if [[ "$OLD_IP" == "$NEW_IP" ]]; then
    log "Old and new IP are identical (${OLD_IP}); nothing to do."
    exit 0
  fi

  SSH_HOST="$OLD_IP"

  # Ensure the cluster is reachable and running before we start
  verify_cluster_running "$KUBECONFIG_EXTERNAL_PATH"

  # Generate install-config and crypto material locally
  fetch_install_config "$INSTALL_CONFIG_PATH" "$KUBECONFIG_EXTERNAL_PATH"

  log "Starting IP change (external host): $OLD_IP -> $NEW_IP (CIDR $NEW_MACHINE_NETWORK)"

  # Derive cluster domain parts for dnsmasq MC
  local cluster_name base_domain
  read -r cluster_name base_domain < <(derive_cluster_domain_parts "$KUBECONFIG_EXTERNAL_PATH" "$INSTALL_CONFIG_PATH")
  if [[ -z "$cluster_name" || -z "$base_domain" ]]; then
    fail "Failed to derive cluster name and base domain from kubeconfig or install-config"
  fi

  # Collect crypto material locally into a temp, then we will copy to node
  local local_crypto_dir local_crypto_json
  local_crypto_dir=$(mktemp -d)
  local_crypto_json=$(mktemp)
  collect_crypto_material "$KUBECONFIG_EXTERNAL_PATH" "$local_crypto_json" "$local_crypto_dir" "$RECERT_CONTAINER_DATA_DIR_PATH"
  log "Collected crypto material to ${local_crypto_dir}, recert config part in ${local_crypto_json}"

  # Prepare derived values
  local prefix iface
  prefix="${NEW_MACHINE_NETWORK##*/}"

  # Detect interface on the SNO node via SSH
  iface=$(detect_remote_br_ex_interface "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING")
  [[ -n "$iface" ]] || fail "Failed to auto-detect interface attached to br-ex on remote node; ensure br-ex exists or install OVS"

  # Generate nmstate temp file locally
  NMSTATE_FILE_PATH=$(create_nmstate_tmp_file "$iface" "$NEW_IP" "$prefix")

  # Apply nmstate MachineConfig from external host only if it would change
  if is_nmstate_mc_up_to_date "$NMSTATE_FILE_PATH" "$KUBECONFIG_EXTERNAL_PATH"; then
    log "Existing nmstate MachineConfig already up-to-date. Skipping apply and MCP wait."
  else
    apply_nmstate_mc "$NMSTATE_FILE_PATH" "$KUBECONFIG_EXTERNAL_PATH"
    # Ensure the MachineConfigPool renders and applies the new configuration
    wait_for_mcp_master_updated "$KUBECONFIG_EXTERNAL_PATH"
    # Wait until node consumes the new rendered MC that includes nmstate changes
    wait_for_node_config_contains_mc "$KUBECONFIG_EXTERNAL_PATH" "$CONTEXT_MSG_NMSTATE_MC"
  fi

  # Stage remote working directory and files
  local remote_dir
  remote_dir=$(prepare_remote_dir "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING")
  log "Prepared remote working directory: ${remote_dir}"

  # Copy required libs and remote runner script
  copy_dir_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/lib" "${remote_dir}/lib"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${SCRIPT_DIR}/remote/${REMOTE_NODE_ACTIONS_FILENAME}" "${remote_dir}/${REMOTE_NODE_ACTIONS_FILENAME}"

  # Copy generated files to the node
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$INSTALL_CONFIG_PATH" "${remote_dir}/${REMOTE_INSTALL_CONFIG_FILENAME}"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$PULL_SECRET_PATH" "${remote_dir}/${REMOTE_PULL_SECRET_FILENAME}"
  copy_dir_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$local_crypto_dir/" "${remote_dir}/${REMOTE_RECERT_DIR_NAME}/"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$local_crypto_json" "${remote_dir}/${REMOTE_RECERT_DIR_NAME}/${REMOTE_RECERT_JSON_NAME}"

  # Always mirror recert image to the node so it can be loaded locally
  local recert_archive_remote_path
  log "Pulling recert image ${RECERT_IMAGE} on external host and mirroring to node"
  local local_recert_tar
  local_recert_tar=$(mktemp --suffix .tar)
  podman pull --authfile "$PULL_SECRET_PATH" "$RECERT_IMAGE"
  podman save -o "$local_recert_tar" "$RECERT_IMAGE"
  local remote_path
  remote_path="${remote_dir}/recert-image.tar"
  copy_to_remote "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$local_recert_tar" "$remote_path"
  recert_archive_remote_path="$remote_path"

  # Execute remote actions as root
  local remote_cmd
  remote_cmd=("sudo" "bash" "${remote_dir}/${REMOTE_NODE_ACTIONS_FILENAME}"
    "--old-ip" "$OLD_IP"
    "--new-ip" "$NEW_IP"
    "--new-machine-network" "$NEW_MACHINE_NETWORK"
    "--install-config" "${remote_dir}/${REMOTE_INSTALL_CONFIG_FILENAME}"
    "--pull-secret-path" "${remote_dir}/${REMOTE_PULL_SECRET_FILENAME}"
    "--recert-image" "$RECERT_IMAGE"
    "--recert-container-data-dir-path" "$RECERT_CONTAINER_DATA_DIR_PATH"
    "--crypto-json-path" "${remote_dir}/${REMOTE_RECERT_DIR_NAME}/${REMOTE_RECERT_JSON_NAME}"
    "--crypto-dir-path" "${remote_dir}/${REMOTE_RECERT_DIR_NAME}/"
    "--primary-ip-path" "$PRIMARY_IP_PATH"
    "--nodeip-defaults-path" "$NODEIP_DEFAULTS_PATH"
    "--nodeip-rerun-unit-path" "$NODEIP_RERUN_UNIT_PATH"
  )
  if [[ -n "$recert_archive_remote_path" ]]; then
    remote_cmd+=("--recert-image-archive" "$recert_archive_remote_path")
  fi
  ssh_exec "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "${remote_cmd[@]}"

  SSH_HOST="$NEW_IP"

  log "Waiting for node SSH on new IP ${SSH_HOST} after reboot"
  ssh_wait "$SSH_USER" "$SSH_HOST" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" "$SSH_WAIT_TIMEOUT_SECS"
  log "SSH to ${SSH_HOST} was successful"

  update_local_hosts_file "$cluster_name" "$base_domain" "$OLD_IP" "$NEW_IP"
  wait_for_cluster_api "$KUBECONFIG_EXTERNAL_PATH"
  verify_node_internal_ip "$KUBECONFIG_EXTERNAL_PATH" "$NEW_IP"

  log "The node IP address is now ${NEW_IP}."
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
