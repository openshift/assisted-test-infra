#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC1091

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/util.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/util.sh"

OLD_IP=""
NEW_IP=""
ORIGINAL_ARGS=("$@")
NEW_MACHINE_NETWORK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-ip) OLD_IP="$2"; shift 2;;
    --new-ip) NEW_IP="$2"; shift 2;;
    --new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
    -h|--help) print_usage; exit 0;;
    *) shift 1;;
  esac
done

need_cmd ip
[[ -n "$OLD_IP" ]] || fail "--old-ip is required"
[[ -n "$NEW_IP" ]] || fail "--new-ip is required"
[[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required"

# Detect the host device that reaches OLD_IP
DEV="$(ip route get "$OLD_IP" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
if [[ -z "$DEV" ]]; then
  DEV="$(ip -6 route get "$OLD_IP" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi
[[ -n "$DEV" ]] || fail "Failed to auto-detect host device for $OLD_IP"

# Add a route for the new machine network via the detected device (idempotent)
if [[ "$NEW_MACHINE_NETWORK" == *:* ]]; then
  if ! ip -6 route show | grep -qw "^$NEW_MACHINE_NETWORK"; then
    log "Adding IPv6 route $NEW_MACHINE_NETWORK via dev $DEV"
    sudo ip -6 route add "$NEW_MACHINE_NETWORK" dev "$DEV" || true
  else
    log "IPv6 route $NEW_MACHINE_NETWORK already present"
  fi
else
  if ! ip route show | grep -qw "^$NEW_MACHINE_NETWORK"; then
    log "Adding IPv4 route $NEW_MACHINE_NETWORK via dev $DEV"
    sudo ip route add "$NEW_MACHINE_NETWORK" dev "$DEV" || true
  else
    log "IPv4 route $NEW_MACHINE_NETWORK already present"
  fi
fi

log "Invoking ip-change.sh with provided arguments"

# Build pass-through args unchanged
PASS_ARGS=()
PASS_ARGS=("${ORIGINAL_ARGS[@]}")

"${SCRIPT_DIR}/ip-change.sh" "${PASS_ARGS[@]}"
