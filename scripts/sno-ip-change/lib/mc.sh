#!/usr/bin/env bash

set -euo pipefail

# Function: get_node_name
# Purpose: Determine the node name via kubeconfig/oc or local hostname.
# Parameters:
# - $1: kubeconfig path
get_node_name() {
  local kubeconfig="$1"
  # If explicitly provided, use it
  if [[ -n "${NODE_NAME:-}" ]]; then
    echo "$NODE_NAME"
    return 0
  fi
  # Prefer Kubernetes view if available
  if [[ -f "$kubeconfig" ]] && oc get nodes --kubeconfig "$kubeconfig" >/dev/null 2>&1; then
    local name
    name=$(oc get nodes -o jsonpath='{.items[0].metadata.name}' --kubeconfig "$kubeconfig" 2>/dev/null || true)
    if [[ -n "$name" ]]; then
      echo "$name"
      return 0
    fi
  fi
  # Fallback to system hostname
  hostname -f 2>/dev/null || hostname
}

# Function: generate_mc_from_nmstate
# Purpose: Build a MachineConfig YAML embedding the given nmstate file.
# Parameters:
# - $1: nmstate file path
# - $2: node name
generate_mc_from_nmstate() {
  local nmstate_file="$1"
  local node_name="$2"
  local mc_name="10-br-ex-${node_name}"
  [[ -f "$nmstate_file" ]] || fail "nmstate file not found: $nmstate_file"
  local b64
  b64=$(base64 -w0 < "$nmstate_file")
  cat <<YAML
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  labels:
    machineconfiguration.openshift.io/role: master
  name: ${mc_name}
spec:
  config:
    ignition:
      version: 3.2.0
    storage:
      files:
      - contents:
          source: data:text/plain;charset=utf-8;base64,${b64}
        mode: 0644
        overwrite: true
        path: /etc/nmstate/openshift/${node_name}.yml
YAML
}

# Function: is_nmstate_mc_up_to_date
# Purpose: Compare existing MC payload with the expected nmstate file.
# Parameters:
# - $1: nmstate file path
# - $2: kubeconfig path
is_nmstate_mc_up_to_date() {
  local nmstate_file="$1"
  local kubeconfig="$2"
  local node_name mc_name b64_expected b64_current src
  node_name=$(get_node_name "$kubeconfig")
  mc_name="10-br-ex-${node_name}"
  [[ -f "$nmstate_file" ]] || return 1
  b64_expected=$(base64 -w0 < "$nmstate_file")
  # Extract the base64 payload from the existing MC, if any
  src=$(oc --kubeconfig "$kubeconfig" get mc "$mc_name" -o jsonpath='{.spec.config.storage.files[0].contents.source}' 2>/dev/null || true)
  if [[ -z "$src" ]]; then
    return 1
  fi
  b64_current="${src##*base64,}"
  [[ "$b64_current" == "$b64_expected" ]]
}

# Function: wait_for_mcp_master_updated
# Purpose: Wait until the master MCP rolls out a new rendered configuration.
# Parameters:
# - $1: kubeconfig path
wait_for_mcp_master_updated() {
  local kubeconfig="$1"
  need_cmd oc
  log "Waiting for MachineConfigPool/master to roll out a new rendered configuration"

  local timeout_secs=900
  local start_ts now_ts
  start_ts=$(date +%s)

  local prev_rendered rendered updating updated degraded
  prev_rendered=$(oc --kubeconfig "$kubeconfig" get mcp master -o jsonpath='{.status.configuration.name}' 2>/dev/null || echo "")
  log "Current MCP/master rendered: ${prev_rendered}"

  # Phase 1: Detect a change starting (either Updating=True or rendered name changed)
  while true; do
    rendered=$(oc --kubeconfig "$kubeconfig" get mcp master -o jsonpath='{.status.configuration.name}' 2>/dev/null || echo "")
    updating=$(oc --kubeconfig "$kubeconfig" get mcp master -o jsonpath='{range .status.conditions[?(@.type=="Updating")]}{.status}{end}' 2>/dev/null || echo "")
    if [[ "$rendered" != "$prev_rendered" || "$updating" == "True" ]]; then
      break
    fi
    now_ts=$(date +%s)
    if (( now_ts - start_ts > timeout_secs )); then
      log "Timeout waiting for MCP master to start updating. Showing status:"
      oc --kubeconfig "$kubeconfig" get mcp master -o yaml | sed -n '1,160p' || true
      fail "Timed out waiting for MCP master to begin rollout"
    fi
    sleep 5
  done

  # Phase 2: Wait until the pool reports Updated=True, Degraded!=True AND rendered changed
  while true; do
    rendered=$(oc --kubeconfig "$kubeconfig" get mcp master -o jsonpath='{.status.configuration.name}' 2>/dev/null || echo "")
    updated=$(oc --kubeconfig "$kubeconfig" get mcp master -o jsonpath='{range .status.conditions[?(@.type=="Updated")]}{.status}{end}' 2>/dev/null || echo "")
    degraded=$(oc --kubeconfig "$kubeconfig" get mcp master -o jsonpath='{range .status.conditions[?(@.type=="Degraded")]}{.status}{end}' 2>/dev/null || echo "")
    if [[ -n "$rendered" && "$rendered" != "$prev_rendered" && "$updated" == "True" && "$degraded" != "True" ]]; then
      log "MachineConfigPool master rolled out new rendered ${rendered} (previous ${prev_rendered})."
      break
    fi
    now_ts=$(date +%s)
    if (( now_ts - start_ts > timeout_secs )); then
      log "Timeout waiting for MCP master to finish rollout. Showing status:"
      oc --kubeconfig "$kubeconfig" get mcp master -o yaml | sed -n '1,200p' || true
      fail "Timed out waiting for MCP master to reach Updated with new rendered config"
    fi
    sleep 10
  done
}

# Function: apply_nmstate_mc
# Purpose: Apply MachineConfig to write nmstate content on the node.
# Parameters:
# - $1: nmstate file path
# - $2: kubeconfig path
apply_nmstate_mc() {
  local nmstate_file="$1"
  local kubeconfig="$2"
  need_cmd base64
  local node_name
  node_name=$(get_node_name "$kubeconfig")
  [[ -n "$node_name" ]] || fail "Failed to determine node name"
  log "Applying MachineConfig to write nmstate for node ${node_name}"
  if is_nmstate_mc_up_to_date "$nmstate_file" "$kubeconfig"; then
    log "Existing nmstate MachineConfig already up-to-date. Skipping apply."
    return 0
  fi
  local tmpfile
  tmpfile=$(mktemp)
  generate_mc_from_nmstate "$nmstate_file" "$node_name" > "$tmpfile"
  oc_retry "$kubeconfig" apply -f "$tmpfile"
  rm -f "$tmpfile"
  # Short settle; higher-level logic handles reboots/file checks
  sleep 3
}

# Function: wait_for_nmstate_file
# Purpose: Wait until the node nmstate file appears and includes expected IP.
# Parameters:
# - $1: kubeconfig path
# - $2: expected IPv4 address
wait_for_nmstate_file() {
  local kubeconfig="$1"
  local expected_ip="$2"
  local node_name
  node_name=$(get_node_name "$kubeconfig")
  [[ -n "$node_name" ]] || fail "Failed to determine node name"
  local path="/etc/nmstate/openshift/${node_name}.yml"
  log "Waiting for nmstate file to be present at ${path}"
  local start
  start=$(date +%s)
  local timeout=300
  while true; do
    if [[ -f "$path" ]]; then
      if grep -q "$expected_ip" "$path"; then
        log "nmstate file present and contains expected IP ${expected_ip}"
        break
      fi
    fi
    local now
    now=$(date +%s)
    if (( now - start > timeout )); then
      log "Timeout waiting for ${path}. Current state:"
      ls -l /etc/nmstate/openshift/ || true
      if [[ -f "$path" ]]; then sed -n '1,120p' "$path"; fi
      break
    fi
    sleep 5
  done
}


# Wait until the node's desiredConfig and currentConfig annotations reflect the
# latest rendered configuration from the master MachineConfigPool. This ensures
# that a newly applied MC has been rendered by MCO and fully rolled out to the node.
# Function: wait_for_node_config_contains_mc
# Purpose: Wait for node desired/current config to match latest rendered MCP.
# Parameters:
# - $1: kubeconfig path
# - $2: optional context message
wait_for_node_config_contains_mc() {
  local kubeconfig="$1"
  local context_msg="${2:-}"
  need_cmd oc
  need_cmd jq
  local node_name
  node_name=$(get_node_name "$kubeconfig")
  [[ -n "$node_name" ]] || fail "Failed to determine node name"

  local timeout_secs=900
  local start_ts now_ts
  start_ts=$(date +%s)

  local mcp_rendered
  mcp_rendered=$(oc --kubeconfig "$kubeconfig" get mcp master -o json 2>/dev/null | jq -r '.status.configuration.name // ""' || echo "")
  if [[ -n "$context_msg" ]]; then
    log "Waiting for node ${node_name} to apply new MachineConfig (${context_msg})"
  else
    log "Waiting for node ${node_name} to apply new MachineConfig"
  fi

  while true; do
    local desired current
    desired=$(oc --kubeconfig "$kubeconfig" get node "$node_name" -o json 2>/dev/null | jq -r '.metadata.annotations["machineconfiguration.openshift.io/desiredConfig"] // ""' 2>/dev/null || echo "")
    current=$(oc --kubeconfig "$kubeconfig" get node "$node_name" -o json 2>/dev/null | jq -r '.metadata.annotations["machineconfiguration.openshift.io/currentConfig"] // ""' 2>/dev/null || echo "")

    if [[ -n "$mcp_rendered" ]]; then
      if [[ "$desired" == "$mcp_rendered" && "$current" == "$mcp_rendered" ]]; then
        log "Node ${node_name} desiredConfig/currentConfig match MCP configuration ${mcp_rendered}"
        break
      fi
    else
      if [[ -n "$desired" && "$desired" == "$current" ]]; then
        log "Node ${node_name} currentConfig equals desiredConfig (${desired})"
        break
      fi
    fi

    now_ts=$(date +%s)
    if (( now_ts - start_ts > timeout_secs )); then
      log "Timeout waiting for node ${node_name} to apply MachineConfig. Debug info follows."
      oc --kubeconfig "$kubeconfig" get mcp master -o yaml | sed -n '1,120p' || true
      oc --kubeconfig "$kubeconfig" get node "$node_name" -o json | jq '{name:.metadata.name, annotations:{desired:.metadata.annotations["machineconfiguration.openshift.io/desiredConfig"], current:.metadata.annotations["machineconfiguration.openshift.io/currentConfig"], state:.metadata.annotations["machineconfiguration.openshift.io/state"]}}' || true
      fail "Timed out waiting for MachineConfig to apply on node ${node_name}"
    fi

    sleep 10
    # Refresh the MCP rendered config name in case it changed during the loop
    mcp_rendered=$(oc --kubeconfig "$kubeconfig" get mcp master -o json 2>/dev/null | jq -r '.status.configuration.name // ""' || printf "%s" "$mcp_rendered")
  done
}
