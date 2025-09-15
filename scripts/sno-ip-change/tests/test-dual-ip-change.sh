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
# shellcheck source=lib/ssh.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/ssh.sh"

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
PRIMARY_STACK="v4"
KUBECONFIG_EXTERNAL_PATH=""
SSH_USER="core"
SSH_PORT="22"
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_STRICT_HOSTKEY_CHECKING="no"

# Preserve original args to pass through (minus kubeconfig)
ORIGINAL_ARGS=("$@")

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
    --kubeconfig-path) KUBECONFIG_EXTERNAL_PATH="$2"; shift 2;;
    --ssh-user) SSH_USER="$2"; shift 2;;
    --ssh-port) SSH_PORT="$2"; shift 2;;
    --ssh-key) SSH_KEY="$2"; shift 2;;
    --ssh-strict-hostkey-checking) SSH_STRICT_HOSTKEY_CHECKING="$2"; shift 2;;
    -h|--help) echo "Usage: $0 \
      --old-ipv4 <ip> --new-ipv4 <ip> --new-machine-network-v4 <cidr> \
      --old-ipv6 <ip> --new-ipv6 <ip> --new-machine-network-v6 <cidr> \
      --new-gateway-ipv4 <gateway> --new-gateway-ipv6 <gateway> \
      --primary-stack <v4|v6> \
      --recert-image-tar <path> \
      [--new-dns-server-ipv4 <dns>] [--new-dns-server-ipv6 <dns>] \
      [--ssh-user ...] [--ssh-port ...] [--ssh-key ...] \
      --kubeconfig-path <path>"; exit 0;;
    *) shift 1;;
  esac
done

need_cmd ip
need_cmd sed
need_cmd oc
need_cmd ssh

[[ -n "$KUBECONFIG_EXTERNAL_PATH" && -f "$KUBECONFIG_EXTERNAL_PATH" ]] || fail "--kubeconfig-path is required and must exist"

# Early check: cluster API must be reachable before proceeding
log "Checking cluster API reachability using ${KUBECONFIG_EXTERNAL_PATH}"
if ! oc --kubeconfig "$KUBECONFIG_EXTERNAL_PATH" get nodes >/dev/null 2>&1; then
  fail "Cluster API is unreachable with the provided kubeconfig. Aborting."
fi

# Determine host device based on the primary stack old IP, fallback to the other
DEV=""
if [[ "$PRIMARY_STACK" == "v4" && -n "$OLD_IPV4" ]]; then
  DEV="$(ip route get "$OLD_IPV4" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
elif [[ -n "$OLD_IPV6" ]]; then
  DEV="$(ip -6 route get "$OLD_IPV6" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi
if [[ -z "$DEV" && -n "$OLD_IPV4" ]]; then
  DEV="$(ip route get "$OLD_IPV4" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi
if [[ -z "$DEV" && -n "$OLD_IPV6" ]]; then
  DEV="$(ip -6 route get "$OLD_IPV6" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi
[[ -n "$DEV" ]] || fail "Failed to auto-detect host device for provided old IPs"

# Ensure host has addresses for new machine networks (both stacks if provided)
if [[ -n "$NEW_MACHINE_NETWORK_V6" ]]; then
  ipv6_base="${NEW_MACHINE_NETWORK_V6%%/*}"
  ipv6_prefix="${NEW_MACHINE_NETWORK_V6##*/}"
  if [[ "$NEW_MACHINE_NETWORK_V6" != */* ]]; then
    ipv6_prefix=""
  fi
  if [[ "$ipv6_base" == *::* ]]; then
    base_left="${ipv6_base%%::*}"
    if [[ -n "$base_left" ]]; then
      device_addr="$base_left::1"
    else
      device_addr="::1"
    fi
  else
    device_addr="${ipv6_base%:*}:1"
  fi
  device_cidr="$device_addr"
  if [[ -n "$ipv6_prefix" && "$ipv6_prefix" != "$NEW_MACHINE_NETWORK_V6" ]]; then
    device_cidr="$device_addr/$ipv6_prefix"
  fi
  if ! ip -6 -o addr show dev "$DEV" | awk '{print $4}' | grep -qw "$device_cidr"; then
    log "Adding IPv6 address $device_cidr to $DEV"
    sudo ip -6 addr add "$device_cidr" dev "$DEV" || true
  else
    log "IPv6 address $device_cidr already present on $DEV"
  fi
fi

if [[ -n "$NEW_MACHINE_NETWORK_V4" ]]; then
  ipv4_base="${NEW_MACHINE_NETWORK_V4%%/*}"
  ipv4_prefix="${NEW_MACHINE_NETWORK_V4##*/}"
  if [[ "$NEW_MACHINE_NETWORK_V4" != */* ]]; then
    ipv4_prefix=""
  fi
  device_addr="${ipv4_base%.*}.1"
  device_cidr="$device_addr"
  if [[ -n "$ipv4_prefix" && "$ipv4_prefix" != "$NEW_MACHINE_NETWORK_V4" ]]; then
    device_cidr="$device_addr/$ipv4_prefix"
  fi
  if ! ip -4 -o addr show dev "$DEV" | awk '{print $4}' | grep -qw "$device_cidr"; then
    log "Adding IPv4 address $device_cidr to $DEV"
    sudo ip addr add "$device_cidr" dev "$DEV" || true
  else
    log "IPv4 address $device_cidr already present on $DEV"
  fi
fi

cluster_name=""; base_domain=""
read -r cluster_name base_domain < <(derive_cluster_domain_parts "$KUBECONFIG_EXTERNAL_PATH" "")
if [[ -n "$cluster_name" && -n "$base_domain" ]]; then
  if [[ -n "$OLD_IPV4" && -n "$NEW_IPV4" ]]; then
    update_local_hosts_file "$cluster_name" "$base_domain" "$OLD_IPV4" "$NEW_IPV4"
  fi
  if [[ -n "$OLD_IPV6" && -n "$NEW_IPV6" ]]; then
    update_local_hosts_file "$cluster_name" "$base_domain" "$OLD_IPV6" "$NEW_IPV6"
  fi
else
  log "WARNING: Could not update /etc/hosts (missing cluster/domain); skipping"
fi

PASS_ARGS=()
skip_next="false"
for idx in "${!ORIGINAL_ARGS[@]}"; do
  if [[ "$skip_next" == "true" ]]; then
    skip_next="false"
    continue
  fi
  arg="${ORIGINAL_ARGS[$idx]}"
  if [[ "$arg" == "--kubeconfig-path" ]]; then
    skip_next="true"
    continue
  fi
  PASS_ARGS+=("$arg")
done

log "Invoking dual-ip-change.sh with provided arguments"
"${SCRIPT_DIR}/flows/dual-ip-change.sh" "${PASS_ARGS[@]}"

if [[ "$PRIMARY_STACK" == "v4" ]]; then
  OLD_SSH_IP="$OLD_IPV4"
  NEW_SSH_IP="$NEW_IPV4"
else
  OLD_SSH_IP="$OLD_IPV6"
  NEW_SSH_IP="$NEW_IPV6"
fi

log "Triggering remote reboot on ${OLD_SSH_IP}"
ssh_exec "$SSH_USER" "$OLD_SSH_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" sudo reboot

log "Waiting for SSH to become available on new IP ${NEW_SSH_IP}"
ssh_wait "$SSH_USER" "$NEW_SSH_IP" "$SSH_PORT" "$SSH_KEY" "$SSH_STRICT_HOSTKEY_CHECKING" 900

wait_for_cluster_api "$KUBECONFIG_EXTERNAL_PATH"
verify_node_internal_ips "$KUBECONFIG_EXTERNAL_PATH" "${NEW_IPV4:-}" "${NEW_IPV6:-}"

log "IP change test completed successfully. New IPv4: ${NEW_IPV4:-N/A}, New IPv6: ${NEW_IPV6:-N/A}"
