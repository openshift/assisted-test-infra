#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC1091

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/util.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/util.sh"
# shellcheck source=lib/cluster.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/cluster.sh"

OLD_IP=""
NEW_IP=""
NEW_MACHINE_NETWORK=""
KUBECONFIG_EXTERNAL_PATH=""
SSH_USER="core"
SSH_PORT="22"
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_STRICT_HOSTKEY_CHECKING="no"

# Preserve original args to pass through (minus kubeconfig and host-only args)
ORIGINAL_ARGS=("$@")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ip) OLD_IP="$2"; shift 2;;
    --new-ip) NEW_IP="$2"; shift 2;;
    --new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
    --kubeconfig-path) KUBECONFIG_EXTERNAL_PATH="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --ssh-strict-hostkey-checking) SSH_STRICT_HOSTKEY_CHECKING="$2"; shift 2;;
    -h|--help)
      echo "Usage: $0 --old-ip <ip> --new-ip <ip> --new-machine-network <cidr> --kubeconfig-path <path> [--ssh-user ...] [--ssh-port ...] [--ssh-key ...] [--ssh-strict-hostkey-checking yes|no]";
      exit 0;;
    *) shift 1;;
  esac
done

need_cmd ip
need_cmd sed
need_cmd oc

[[ -n "$KUBECONFIG_EXTERNAL_PATH" && -f "$KUBECONFIG_EXTERNAL_PATH" ]] || fail "--kubeconfig-path is required and must exist"
[[ -n "$OLD_IP" ]] || fail "--old-ip is required"
[[ -n "$NEW_IP" ]] || fail "--new-ip is required"
[[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required"

# Early check: cluster API must be reachable before proceeding
log "Checking cluster API reachability using ${KUBECONFIG_EXTERNAL_PATH}"
if ! oc --kubeconfig "$KUBECONFIG_EXTERNAL_PATH" get nodes >/dev/null 2>&1; then
  fail "Cluster API is unreachable with the provided kubeconfig. Aborting."
fi

# Determine host device based on the old IP (v4 or v6)
DEV=""
DEV="$(ip route get "$OLD_IP" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
if [[ -z "$DEV" ]]; then
  DEV="$(ip -6 route get "$OLD_IP" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi
[[ -n "$DEV" ]] || fail "Failed to auto-detect host device for provided old IP"

# Ensure host has an address in the new machine network (idempotent)
if [[ "$NEW_MACHINE_NETWORK" == *:* ]]; then
  ipv6_base="${NEW_MACHINE_NETWORK%%/*}"
  ipv6_prefix="${NEW_MACHINE_NETWORK##*/}"
  if [[ "$NEW_MACHINE_NETWORK" != */* ]]; then
    ipv6_prefix=""
  fi
  if [[ "$ipv6_base" == *::* ]]; then
    base_left="${ipv6_base%%::*}"
    if [[ -n "$base_left" ]]; then
      device_addr="${base_left}::1"
    else
      device_addr="::1"
    fi
  else
    device_addr="${ipv6_base%:*}:1"
  fi
  device_cidr="$device_addr"
  if [[ -n "$ipv6_prefix" && "$ipv6_prefix" != "$NEW_MACHINE_NETWORK" ]]; then
    device_cidr="$device_addr/$ipv6_prefix"
  fi
  if ! ip -6 -o addr show dev "$DEV" | awk '{print $4}' | grep -qw "$device_cidr"; then
    log "Adding IPv6 address $device_cidr to $DEV"
    sudo ip -6 addr add "$device_cidr" dev "$DEV" || true
  else
    log "IPv6 address $device_cidr already present on $DEV"
  fi
else
  ipv4_base="${NEW_MACHINE_NETWORK%%/*}"
  ipv4_prefix="${NEW_MACHINE_NETWORK##*/}"
  if [[ "$NEW_MACHINE_NETWORK" != */* ]]; then
    ipv4_prefix=""
  fi
  device_addr="${ipv4_base%.*}.1"
  device_cidr="$device_addr"
  if [[ -n "$ipv4_prefix" && "$ipv4_prefix" != "$NEW_MACHINE_NETWORK" ]]; then
    device_cidr="$device_addr/$ipv4_prefix"
  fi
  if ! ip -4 -o addr show dev "$DEV" | awk '{print $4}' | grep -qw "$device_cidr"; then
    log "Adding IPv4 address $device_cidr to $DEV"
    sudo ip addr add "$device_cidr" dev "$DEV" || true
  else
    log "IPv4 address $device_cidr already present on $DEV"
  fi
fi

# Attempt to update /etc/hosts
cluster_name=""; base_domain=""
read -r cluster_name base_domain < <(derive_cluster_domain_parts "$KUBECONFIG_EXTERNAL_PATH" "")
if [[ -n "$cluster_name" && -n "$base_domain" ]]; then
  update_local_hosts_file "$cluster_name" "$base_domain" "$OLD_IP" "$NEW_IP"
else
  log "WARNING: Could not update /etc/hosts (missing cluster/domain); skipping"
fi

# Build pass-through args: remove host-only flags (kubeconfig, new-machine-network)
PASS_ARGS=()
skip_next="false"
for idx in "${!ORIGINAL_ARGS[@]}"; do
  if [[ "$skip_next" == "true" ]]; then
    skip_next="false"
    continue
  fi
  arg="${ORIGINAL_ARGS[$idx]}"
  if [[ "$arg" == "--kubeconfig-path" || "$arg" == "--new-machine-network" ]]; then
    skip_next="true"
    continue
  fi
  PASS_ARGS+=("$arg")
done

log "Invoking secondary-ip-change.sh with provided arguments"
"${SCRIPT_DIR}/flows/secondary-ip-change.sh" "${PASS_ARGS[@]}" --new-machine-network "$NEW_MACHINE_NETWORK"

# After flow completes (includes two reboots and SSH wait), wait for cluster API
wait_for_cluster_api "$KUBECONFIG_EXTERNAL_PATH"

# Verify the node InternalIP list contains the new IP
if [[ "$NEW_IP" == *:* ]]; then
  verify_node_internal_ips "$KUBECONFIG_EXTERNAL_PATH" "" "$NEW_IP"
else
  verify_node_internal_ips "$KUBECONFIG_EXTERNAL_PATH" "$NEW_IP" ""
fi

log "Secondary IP change test completed successfully. New IP: ${NEW_IP}"


