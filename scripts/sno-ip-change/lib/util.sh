#!/usr/bin/env bash

set -euo pipefail

# Function: log
# Purpose: Print a timestamped log line to stderr.
# Parameters:
# - $*: Message to log
log() {
  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" >&2
}

# Function: fail
# Purpose: Log an error message and exit with status 1.
# Parameters:
# - $*: Error message
fail() {
  log "ERROR: $*"
  exit 1
}

# Function: need_cmd
# Purpose: Ensure a required executable is present in PATH.
# Parameters:
# - $1: Command name to check
need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

# Function: require_root
# Purpose: Abort unless running as root.
require_root() {
  if [[ $(id -u) -ne 0 ]]; then
    fail "Must run as root (use sudo)."
  fi
}

# Function: systemd_reload
# Purpose: Reload systemd manager configuration.
systemd_reload() {
  log "Reloading systemd daemon"
  systemctl daemon-reload
}

# Function: reboot_node
# Purpose: Initiate a system reboot.
reboot_node() {
  log "Rebooting node now to apply network changes"
  sync || true
  systemctl reboot
}

# Function: is_ipv4_address
# Purpose: Return 0 if the input is a valid-looking IPv4 literal
is_ipv4_address() {
  local ip="$1"
  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

# Function: is_ipv6_address
# Purpose: Return 0 if the input contains ':' and resembles an IPv6 literal
is_ipv6_address() {
  local ip="$1"
  [[ "$ip" == *:* ]]
}

# Function: ensure_kubelet_enabled
# Purpose: Enable kubelet.service if not already enabled.
ensure_kubelet_enabled() {
  log "Ensuring kubelet is enabled for next boot"
  systemctl is-enabled --quiet kubelet.service || systemctl enable kubelet.service || true
}


# Function: oc_retry
# Purpose: Retry an oc command with a kubeconfig for a limited number of attempts.
# Parameters:
# - $1: kubeconfig path
# - $@: oc subcommand and arguments
oc_retry() {
  local kubeconfig="$1"; shift
  local attempts="${OC_RETRY_ATTEMPTS:-10}"
  local delay_secs="${OC_RETRY_DELAY_SECS:-5}"
  local attempt_idx
  for ((attempt_idx=1; attempt_idx<=attempts; attempt_idx++)); do
    if oc --kubeconfig "$kubeconfig" "$@"; then
      return 0
    fi
    sleep "$delay_secs"
  done
  return 1
}

# Function: start_cluster_services
# Purpose: Start kubelet and crio and optionally wait for API.
# Parameters:
# - $1: kubeconfig path (optional). If provided, waits for API.
start_cluster_services() {
  local kubeconfig="${1:-}"
  ensure_kubelet_enabled || true
  systemctl start kubelet.service || true
  systemctl start crio.service || true
  if [[ -n "$kubeconfig" ]]; then
    wait_for_cluster_api "$kubeconfig" || true
  fi
}

# Function: attempt_full_rollback
# Purpose: Best-effort rollback to pre-run state: restore crypto, revert dnsmasq IP,
#          bring cluster back up, and remove per-node nmstate MC.
# Parameters:
# - $1: backup directory path
# - $2: recert image reference
# - $3: kubeconfig path (internal)
# - $4: old IPv4 address
attempt_full_rollback() {
  local backup_dir="$1"
  local recert_image="$2"
  local kubeconfig="$3"
  local old_ipv4="$4"

  # restore_seed_crypto, set_dnsmasq_new_ip_override, delete_nmstate_mc, wait_for_cluster_api
  # are defined in other libs that should be sourced by the caller script.
  log "Starting best-effort rollback using backup at ${backup_dir}"
  restore_seed_crypto "$backup_dir" "$recert_image" "" || true
  set_dnsmasq_new_ip_override "$old_ipv4" || true

  ensure_kubelet_enabled || true
  systemctl start kubelet.service || true
  systemctl start crio.service || true

  wait_for_cluster_api "$kubeconfig" || true
  delete_nmstate_mc "$kubeconfig" || true
  log "Rollback attempts completed"
}
