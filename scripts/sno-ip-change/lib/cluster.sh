#!/usr/bin/env bash

set -euo pipefail

# Function: derive_cluster_domain_parts
# Purpose: Determine cluster name and baseDomain via oc or install-config.
# Parameters:
# - $1: kubeconfig path
# - $2: install-config path
# Returns: Prints "<cluster_name> <base_domain>"
derive_cluster_domain_parts() {
  local kubeconfig="$1"
  local install_config_path="$2"
  local ingress cluster_name base_domain trimmed

  if [[ -f "$kubeconfig" ]] && command -v oc >/dev/null 2>&1; then
    ingress=$(oc --kubeconfig "$kubeconfig" get ingresses.config/cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true)
  else
    ingress=""
  fi

  if [[ -n "$ingress" ]]; then
    trimmed="${ingress#apps.}"
    if [[ "$trimmed" == *.* ]]; then
      cluster_name=${trimmed%%.*}
      base_domain=${trimmed#*.}
    fi
  fi

  if [[ -z "${cluster_name:-}" || -z "${base_domain:-}" ]]; then
    if [[ -f "$install_config_path" ]]; then
      base_domain=$(awk '/^\s*baseDomain:/ {print $2; exit}' "$install_config_path" 2>/dev/null || true)
      cluster_name=$(awk '/^\s*name:/ {print $2; exit}' "$install_config_path" 2>/dev/null || true)
    fi
  fi

  echo "${cluster_name} ${base_domain}"
}


# Function: verify_cluster_running
# Purpose: Ensure cluster API is reachable and at least one node is Ready.
# Parameters:
# - $1: kubeconfig path
verify_cluster_running() {
  local kubeconfig="$1"
  log "Verifying cluster API is reachable and node is Ready"
  if ! oc --kubeconfig "$kubeconfig" get nodes >/dev/null 2>&1; then
    fail "Cluster API is unreachable with the provided kubeconfig"
  fi
  local ready
  ready=$(oc --kubeconfig "$kubeconfig" get nodes -o jsonpath='{range .items[*]}{range .status.conditions[?(@.type=="Ready")]}{.status}{"\n"}{end}{end}' 2>/dev/null | grep -c '^True$' || true)
  if [[ -z "$ready" || "$ready" -lt 1 ]]; then
    fail "No Ready nodes reported by the cluster. Ensure the cluster is healthy before proceeding."
  fi
  log "Cluster is reachable; ${ready} node(s) are Ready."
}

# Function: verify_node_internal_ip
# Purpose: Wait until the node InternalIP equals the expected new IP.
# Parameters:
# - $1: kubeconfig path
# - $2: expected IPv4 address
verify_node_internal_ip() {
  local kubeconfig="$1"
  local expected_ip="$2"
  local timeout_secs=1200
  local start_ts now_ts current_ip
  start_ts=$(date +%s)
  log "Waiting for node InternalIP to become ${expected_ip}"
  while true; do
    if oc --kubeconfig "$kubeconfig" get nodes >/dev/null 2>&1; then
      current_ip=$(oc --kubeconfig "$kubeconfig" get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
      if [[ "$current_ip" == "$expected_ip" ]]; then
        log "InternalIP is updated to ${expected_ip}."
        break
      fi
    fi
    now_ts=$(date +%s)
    if (( now_ts - start_ts > timeout_secs )); then
      log "Timeout waiting for InternalIP to update. Current node status:"
      oc --kubeconfig "$kubeconfig" get node -o wide || true
      break
    fi
    sleep 10
  done
}

# Function: verify_node_internal_ips
# Purpose: Wait until the node InternalIP list contains the provided IPv4 and/or IPv6 addresses.
# Parameters:
# - $1: kubeconfig path
# - $2: expected IPv4 address (optional)
# - $3: expected IPv6 address (optional)
verify_node_internal_ips() {
  local kubeconfig="$1"
  local expected_v4="${2:-}"
  local expected_v6="${3:-}"
  local timeout_secs=1200
  local start_ts now_ts
  start_ts=$(date +%s)

  local expect_desc
  expect_desc=""
  if [[ -n "$expected_v4" ]]; then expect_desc+="v4=${expected_v4} "; fi
  if [[ -n "$expected_v6" ]]; then expect_desc+="v6=${expected_v6}"; fi
  log "Waiting for node InternalIP list to contain: ${expect_desc}"

  while true; do
    if oc --kubeconfig "$kubeconfig" get nodes >/dev/null 2>&1; then
      # newline-separated list of InternalIP addresses
      mapfile -t internal_ips < <(oc --kubeconfig "$kubeconfig" get node -o jsonpath='{range .items[0].status.addresses[?(@.type=="InternalIP")]}{.address}{"\n"}{end}' 2>/dev/null || true)
      local have_v4 have_v6
      have_v4="true"
      have_v6="true"
      if [[ -n "$expected_v4" ]]; then
        have_v4="false"
        for addr in "${internal_ips[@]}"; do
          if [[ "$addr" == "$expected_v4" ]]; then have_v4="true"; break; fi
        done
      fi
      if [[ -n "$expected_v6" ]]; then
        have_v6="false"
        for addr in "${internal_ips[@]}"; do
          if [[ "$addr" == "$expected_v6" ]]; then have_v6="true"; break; fi
        done
      fi
      if [[ "$have_v4" == "true" && "$have_v6" == "true" ]]; then
        log "InternalIP list now contains required addresses: ${expect_desc}"
        break
      fi
    fi
    now_ts=$(date +%s)
    if (( now_ts - start_ts > timeout_secs )); then
      log "Timeout waiting for InternalIP list. Current node addresses:"
      oc --kubeconfig "$kubeconfig" get node -o jsonpath='{.items[0].status.addresses}' | sed -n '1,200p' || true
      break
    fi
    sleep 10
  done
}

# Function: wait_for_cluster_api
# Purpose: Wait for 'oc get nodes' to succeed within a timeout.
# Parameters:
# - $1: kubeconfig path
wait_for_cluster_api() {
  local kubeconfig="$1"
  local attempts=120
  local delay=5
  log "Waiting for cluster API to come back after final reboot"
  local attempt_idx
  for ((attempt_idx=1; attempt_idx<=attempts; attempt_idx++)); do
    if oc --kubeconfig "$kubeconfig" get nodes >/dev/null 2>&1; then
      log "Cluster API is responding"
      return 0
    fi
    sleep "$delay"
  done
  log "Cluster API did not respond within $((attempts*delay)) seconds"
  return 1
}

# Function: update_local_hosts_file
# Purpose: Update /etc/hosts entries for cluster domains to point to new IP.
# Parameters:
# - $1: cluster name
# - $2: base domain
# - $3: old IPv4 address
# - $4: new IPv4 address
update_local_hosts_file() {
  local cluster_name="$1"
  local base_domain="$2"
  local old_ip="$3"
  local new_ip="$4"
  local hosts_file="/etc/hosts"
  local domain
  domain="${cluster_name}.${base_domain}"
  # Use sed with '|' delimiter to avoid issues with ':' in IPv6 and '.' in IPv4
  local escaped_domain
  escaped_domain="${domain//\./\\.}"

  # Determine if we need sudo
  local SUDO
  if [[ -w "$hosts_file" ]]; then
    SUDO=""
  else
    if command -v sudo >/dev/null 2>&1; then
      SUDO="sudo"
    else
      log "WARNING: Cannot modify ${hosts_file} (no write permission and sudo not found). Skipping hosts update."
      return 0
    fi
  fi

  # Backup once if not present
  $SUDO cp -n "$hosts_file" "${hosts_file}.bak" || true

  # Replace old IP with new IP only on lines that reference cluster domains
  $SUDO sed -i \
    -e "/\\bapi\\.${escaped_domain}\\b/ s|${old_ip}|${new_ip}|g" \
    -e "/\\bapi-int\\.${escaped_domain}\\b/ s|${old_ip}|${new_ip}|g" \
    -e "/\\.apps\\.${escaped_domain}\\b/ s|${old_ip}|${new_ip}|g" \
    "$hosts_file" || true

  log "Updated ${hosts_file} entries for ${domain} to ${new_ip} (backup at ${hosts_file}.bak)"
}
