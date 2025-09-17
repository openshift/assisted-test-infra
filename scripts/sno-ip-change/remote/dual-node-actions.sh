#!/usr/bin/env bash

set -Eeuo pipefail

# shellcheck disable=SC1091

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
# shellcheck source=lib/util.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/util.sh"
# shellcheck source=lib/network.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/network.sh"
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
# shellcheck source=lib/mc.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/mc.sh"

OLD_IPV4=""
NEW_IPV4=""
NEW_MACHINE_NETWORK_V4=""
OLD_IPV6=""
NEW_IPV6=""
NEW_MACHINE_NETWORK_V6=""
NEW_GATEWAY_IPV4=""
NEW_GATEWAY_IPV6=""
NEW_DNS_SERVER_IPV4=""
NEW_DNS_SERVER_IPV6=""
PRIMARY_STACK="v4" # v4|v6
RECERT_IMAGE="quay.io/dmanor/recert:demo"
RECERT_CONFIG_PATH="$(mktemp)"
RECERT_CONTAINER_DATA_DIR_PATH="/data"
RECERT_IMAGE_ARCHIVE_PATH=""
PRIMARY_IP_PATH="/run/nodeip-configuration/primary-ip"
NODEIP_DEFAULTS_PATH="/etc/default/nodeip-configuration"
NODEIP_RERUN_UNIT_PATH="/etc/systemd/system/sno-nodeip-rerun.service"
KUBECONFIG_INTERNAL_PATH="/etc/kubernetes/static-pod-resources/kube-apiserver-certs/secrets/node-kubeconfigs/lb-ext.kubeconfig"
BACKUP_DIR="/var/tmp/backupCertsDir"
RESTORE_ON_ERROR="true"
# shellcheck disable=SC2034
backup_completed="false"
# shellcheck disable=SC2034
script_completed="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ipv4) OLD_IPV4="$2"; shift 2;;
    --new-ipv4) NEW_IPV4="$2"; shift 2;;
    --new-machine-network-v4) NEW_MACHINE_NETWORK_V4="$2"; shift 2;;
    --old-ipv6) OLD_IPV6="$2"; shift 2;;
    --new-ipv6) NEW_IPV6="$2"; shift 2;;
    --new-machine-network-v6) NEW_MACHINE_NETWORK_V6="$2"; shift 2;;
    --new-gateway-ipv4) NEW_GATEWAY_IPV4="$2"; shift 2;;
    --new-gateway-ipv6) NEW_GATEWAY_IPV6="$2"; shift 2;;
    --new-dns-server-ipv4) NEW_DNS_SERVER_IPV4="$2"; shift 2;;
    --new-dns-server-ipv6) NEW_DNS_SERVER_IPV6="$2"; shift 2;;
    --primary-stack) PRIMARY_STACK="$2"; shift 2;;
    --recert-image) RECERT_IMAGE="$2"; shift 2;;
    --recert-container-data-dir-path) RECERT_CONTAINER_DATA_DIR_PATH="$2"; shift 2;;
    --primary-ip-path) PRIMARY_IP_PATH="$2"; shift 2;;
    --nodeip-defaults-path) NODEIP_DEFAULTS_PATH="$2"; shift 2;;
    --nodeip-rerun-unit-path) NODEIP_RERUN_UNIT_PATH="$2"; shift 2;;
    --recert-image-archive) RECERT_IMAGE_ARCHIVE_PATH="$2"; shift 2;;
    --backup-dir) # shellcheck disable=SC2034
      BACKUP_DIR="$2"; shift 2;;
    --no-restore-on-error) # shellcheck disable=SC2034
      RESTORE_ON_ERROR="false"; shift 1;;
    *) fail "Unknown argument: $1";;
  esac
done

main() {
  require_root
  need_cmd sed
  need_cmd jq
  need_cmd podman
  need_cmd crictl
  need_cmd systemctl
  need_cmd base64
  need_cmd oc

  [[ -n "$OLD_IPV4" ]] || fail "--old-ipv4 is required"
  [[ -n "$NEW_IPV4" ]] || fail "--new-ipv4 is required"
  [[ -n "$NEW_MACHINE_NETWORK_V4" ]] || fail "--new-machine-network-v4 is required"
  [[ -n "$OLD_IPV6" ]] || fail "--old-ipv6 is required"
  [[ -n "$NEW_IPV6" ]] || fail "--new-ipv6 is required"
  [[ -n "$NEW_MACHINE_NETWORK_V6" ]] || fail "--new-machine-network-v6 is required"
  [[ -n "$NEW_GATEWAY_IPV4" ]] || fail "--new-gateway-ipv4 is required"
  [[ -n "$NEW_GATEWAY_IPV6" ]] || fail "--new-gateway-ipv6 is required"
  [[ "$PRIMARY_STACK" == "v4" || "$PRIMARY_STACK" == "v6" ]] || fail "--primary-stack must be 'v4' or 'v6'"
  [[ -n "$RECERT_CONTAINER_DATA_DIR_PATH" ]] || fail "--recert-container-data-dir-path is required"
  [[ -n "$RECERT_IMAGE_ARCHIVE_PATH" && -f "$RECERT_IMAGE_ARCHIVE_PATH" ]] || fail "--recert-image-archive file missing"
  [[ -f "$KUBECONFIG_INTERNAL_PATH" ]] || fail "Internal kubeconfig not found at $KUBECONFIG_INTERNAL_PATH"

  log "Loading image archive from $RECERT_IMAGE_ARCHIVE_PATH"
  local load_output
  local loaded_ref
  if load_output=$(podman load -i "$RECERT_IMAGE_ARCHIVE_PATH" 2>&1); then
    loaded_ref=$(echo "$load_output" | awk '/Loaded image:/ {print $3; exit}')
    if [[ -n "$loaded_ref" ]]; then
      log "Loaded image ref: $loaded_ref"
      if [[ "$loaded_ref" != "$RECERT_IMAGE" ]]; then
        log "Tagging $loaded_ref as $RECERT_IMAGE"
        podman tag "$loaded_ref" "$RECERT_IMAGE"
      fi
    else
      fail "Could not determine loaded image reference from archive load output"
    fi
  else
    log "ERROR: Failed to load image archive: $load_output"
    return 1
  fi

  local iface nmstate_tmp prefix_v4 prefix_v6
  iface=$(detect_br_ex_interface || true)
  [[ -n "$iface" ]] || fail "Failed to auto-detect interface attached to br-ex or connected ethernet on node"
  prefix_v4="${NEW_MACHINE_NETWORK_V4##*/}"
  prefix_v6="${NEW_MACHINE_NETWORK_V6##*/}"
  nmstate_tmp=$(create_nmstate_tmp_file_dual "$iface" "$NEW_IPV4" "$prefix_v4" "$NEW_IPV6" "$prefix_v6" "$NEW_GATEWAY_IPV4" "$NEW_GATEWAY_IPV6" "$NEW_DNS_SERVER_IPV4" "$NEW_DNS_SERVER_IPV6")
  oc --kubeconfig "$KUBECONFIG_INTERNAL_PATH" get mcp master >/dev/null 2>&1 || fail "Internal API is not reachable via $KUBECONFIG_INTERNAL_PATH"
  log "Applying dual-stack nmstate MachineConfig via internal kubeconfig"
  if is_nmstate_mc_up_to_date "$nmstate_tmp" "$KUBECONFIG_INTERNAL_PATH"; then
    log "nmstate MachineConfig already up-to-date; skipping apply"
  else
    apply_nmstate_mc "$nmstate_tmp" "$KUBECONFIG_INTERNAL_PATH"
    wait_for_mcp_master_updated "$KUBECONFIG_INTERNAL_PATH"
    wait_for_node_config_contains_mc "$KUBECONFIG_INTERNAL_PATH" "nmstate MC"
  fi

  local install_cfg
  install_cfg=$(mktemp)
  fetch_install_config "$install_cfg" "$KUBECONFIG_INTERNAL_PATH"

  local crypto_dir crypto_json
  crypto_dir=$(mktemp -d)
  crypto_json=$(mktemp)
  collect_crypto_material "$KUBECONFIG_INTERNAL_PATH" "$crypto_json" "$crypto_dir" "/data"
  
  ensure_cluster_is_down
  run_etcd_container ""
  run_recert_dual \
    "$RECERT_CONFIG_PATH" \
    "$install_cfg" \
    "" \
    "$RECERT_IMAGE" \
    "$RECERT_CONTAINER_DATA_DIR_PATH" \
    "$OLD_IPV4" \
    "$NEW_IPV4" \
    "$NEW_IPV6" \
    "$OLD_IPV6" \
    "$NEW_MACHINE_NETWORK_V4" \
    "$NEW_MACHINE_NETWORK_V6" \
    "$crypto_json" \
    "$crypto_dir"
  teardown_etcd
  ensure_nmstate_configuration_enabled
  ensure_kubelet_enabled

  local primary_cidr primary_new_ip
  if [[ "$PRIMARY_STACK" == "v4" ]]; then
    primary_cidr="$NEW_MACHINE_NETWORK_V4"
    primary_new_ip="$NEW_IPV4"
  else
    primary_cidr="$NEW_MACHINE_NETWORK_V6"
    primary_new_ip="$NEW_IPV6"
  fi
  
  ensure_nodeip_rerun_service "$PRIMARY_IP_PATH" "$NODEIP_DEFAULTS_PATH" "$primary_cidr" "$NODEIP_RERUN_UNIT_PATH"
  set_dnsmasq_new_ip_override "$primary_new_ip"
  cleanup_nmstate_applied_files
  remove_ovn_cert_folders
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi



