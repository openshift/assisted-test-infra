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

NEW_IP=""
NEW_MACHINE_NETWORK=""
KUBECONFIG_INTERNAL_PATH="/etc/kubernetes/static-pod-resources/kube-apiserver-certs/secrets/node-kubeconfigs/lb-ext.kubeconfig"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --new-ip) NEW_IP="$2"; shift 2;;
    --new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
    -h|--help)
      echo "Usage: $0 --new-ip <ip> --new-machine-network <cidr>"; exit 0;;
    *) shift 1;;
  esac
done

main() {
  require_root
  need_cmd oc
  need_cmd jq
  need_cmd base64

  [[ -n "$NEW_IP" ]] || fail "--new-ip is required"
  [[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required"
  [[ -f "$KUBECONFIG_INTERNAL_PATH" ]] || fail "Internal kubeconfig not found at $KUBECONFIG_INTERNAL_PATH"

  local iface
  iface=$(detect_br_ex_interface || true)
  [[ -n "$iface" ]] || fail "Failed to auto-detect interface attached to br-ex or connected ethernet on node"

  local prefix_len nmstate_tmp
  prefix_len="${NEW_MACHINE_NETWORK##*/}"
  local v4_addr v4_prefix_len v6_addr v6_prefix_len
  if [[ "$NEW_IP" == *:* ]]; then
    # Changing IPv6; preserve existing IPv4
    v6_addr="$NEW_IP"
    v6_prefix_len="$prefix_len"
    # Try to discover existing IPv4 address on br-ex, fallback to the physical iface
    local existing_v4
    existing_v4=$(ip -4 -o addr show dev br-ex scope global 2>/dev/null | awk '{print $4}' | head -n1 || true)
    if [[ -z "$existing_v4" ]]; then
      existing_v4=$(ip -4 -o addr show dev "$iface" scope global 2>/dev/null | awk '{print $4}' | head -n1 || true)
    fi
    [[ -n "$existing_v4" ]] || fail "Dual-stack required: could not find existing IPv4 address on br-ex or ${iface}"
    v4_addr="${existing_v4%%/*}"
    v4_prefix_len="${existing_v4##*/}"
  else
    # Changing IPv4; preserve existing IPv6
    v4_addr="$NEW_IP"
    v4_prefix_len="$prefix_len"
    # Try to discover existing IPv6 address on br-ex, fallback to the physical iface
    local existing_v6
    existing_v6=$(ip -6 -o addr show dev br-ex scope global 2>/dev/null | awk '{print $4}' | head -n1 || true)
    if [[ -z "$existing_v6" ]]; then
      existing_v6=$(ip -6 -o addr show dev "$iface" scope global 2>/dev/null | awk '{print $4}' | head -n1 || true)
    fi
    [[ -n "$existing_v6" ]] || fail "Dual-stack required: could not find existing IPv6 address on br-ex or ${iface}"
    v6_addr="${existing_v6%%/*}"
    v6_prefix_len="${existing_v6##*/}"
  fi

  log "Building dual-stack nmstate configuration for br-ex (v4 ${v4_addr:-none}/${v4_prefix_len:-?}, v6 ${v6_addr:-none}/${v6_prefix_len:-?})"
  nmstate_tmp=$(create_nmstate_tmp_file_dual "$iface" "$v4_addr" "$v4_prefix_len" "$v6_addr" "$v6_prefix_len")

  log "Applying nmstate MachineConfig via internal kubeconfig"
  if is_nmstate_mc_up_to_date "$nmstate_tmp" "$KUBECONFIG_INTERNAL_PATH"; then
    log "nmstate MachineConfig already up-to-date; skipping apply"
  else
    apply_nmstate_mc "$nmstate_tmp" "$KUBECONFIG_INTERNAL_PATH"
    wait_for_mcp_master_updated "$KUBECONFIG_INTERNAL_PATH"
    wait_for_node_config_contains_mc "$KUBECONFIG_INTERNAL_PATH" "nmstate MC"
  fi

  cleanup_nmstate_applied_files
  remove_ovn_cert_folders
  reboot_node || true
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi



