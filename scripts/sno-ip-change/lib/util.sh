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
