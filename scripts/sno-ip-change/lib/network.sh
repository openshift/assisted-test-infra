#!/usr/bin/env bash

set -euo pipefail

# Function: detect_br_ex_interface
# Purpose: Detect an interface attached to br-ex or a connected ethernet.
# Returns: Prints interface name on success; exits non-zero on failure.
detect_br_ex_interface() {
  if command -v ovs-vsctl >/dev/null 2>&1; then
    local ports
    ports=$(ovs-vsctl list-ports br-ex 2>/dev/null || true)
    if [[ -n "$ports" ]]; then
      local p
      for p in $ports; do
        if [[ "$p" != "br-ex" ]]; then
          echo "$p"
          return 0
        fi
      done
    fi
  fi
  if command -v nmcli >/dev/null 2>&1; then
    local iface
    iface=$(nmcli -t -f DEVICE,STATE,CONNECTION device status | awk -F: '$2=="connected"{print $1; exit}' || true)
    if [[ -n "$iface" ]]; then
      echo "$iface"
      return 0
    fi
  fi
  return 1
}

# Function: build_nmstate_yaml
# Purpose: Generate nmstate YAML for moving IP to br-ex and enslaving a NIC.
# Parameters:
# - $1: Physical interface name to enslave into br-ex
# - $2: New IP address for br-ex (IPv4 or IPv6)
# - $3: Prefix length
# - $4: Address family: v4 or v6
build_nmstate_yaml() {
  local interface_name="$1"
  local ip_addr="$2"
  local prefix_len="$3"
  local family="$4"
  if [[ "$family" == "v6" ]]; then
    cat <<YAML
interfaces:
- name: ${interface_name}
  type: ethernet
  state: up
  ipv4:
    enabled: false
  ipv6:
    enabled: false
- name: br-ex
  type: ovs-bridge
  state: up
  ipv4:
    enabled: false
    dhcp: false
  ipv6:
    enabled: false
    dhcp: false
  bridge:
    options:
      mcast-snooping-enable: true
    port:
    - name: ${interface_name}
    - name: br-ex
- name: br-ex
  type: ovs-interface
  state: up
  copy-mac-from: ${interface_name}
  ipv4:
    enabled: false
    dhcp: false
  ipv6:
    enabled: true
    dhcp: false
    address:
    - ip: ${ip_addr}
      prefix-length: ${prefix_len}
    auto-route-metric: 48
YAML
  else
    cat <<YAML
interfaces:
- name: ${interface_name}
  type: ethernet
  state: up
  ipv4:
    enabled: false
  ipv6:
    enabled: false
- name: br-ex
  type: ovs-bridge
  state: up
  ipv4:
    enabled: false
    dhcp: false
  ipv6:
    enabled: false
    dhcp: false
  bridge:
    options:
      mcast-snooping-enable: true
    port:
    - name: ${interface_name}
    - name: br-ex
- name: br-ex
  type: ovs-interface
  state: up
  copy-mac-from: ${interface_name}
  ipv4:
    enabled: true
    dhcp: false
    address:
    - ip: ${ip_addr}
      prefix-length: ${prefix_len}
    auto-route-metric: 48
  ipv6:
    enabled: false
YAML
  fi
}

# Function: create_nmstate_tmp_file
# Purpose: Write nmstate YAML to a temp file and print the path.
# Parameters:
# - $1: Physical interface name
# - $2: New IPv4 address
# - $3: Prefix length
create_nmstate_tmp_file() {
  local interface_name="$1"
  local ip_addr="$2"
  local prefix_len="$3"
  local f
  f=$(mktemp)
  local family
  if is_ipv6_address "$ip_addr"; then
    family="v6"
  else
    family="v4"
  fi
  build_nmstate_yaml "$interface_name" "$ip_addr" "$prefix_len" "$family" > "$f"
  log "Created nmstate configuration at ${f} for ${interface_name} (${ip_addr}/${prefix_len})"
  echo "$f"
}

# Ensure nmstate-configuration is enabled so it runs on boot
# Function: ensure_nmstate_configuration_enabled
# Purpose: Enable nmstate-configuration.service if needed.
ensure_nmstate_configuration_enabled() {
  log "Ensuring nmstate-configuration.service is enabled"
  systemctl is-enabled --quiet nmstate-configuration.service || systemctl enable nmstate-configuration.service || true
  log "nmstate-configuration.service enabled"
}


# Function: ensure_nodeip_rerun_service
# Purpose: Install one-shot service to rerun nodeip-configuration with hint.
# Parameters:
# - $1: Primary IP hint file path
# - $2: nodeip-configuration defaults file path
# - $3: New CIDR
# - $4: Unit file path to write
ensure_nodeip_rerun_service() {
  local primary_ip_path="$1"
  local nodeip_defaults_path="$2"
  local new_machine_network="$3"
  local unit_path="$4"
  local base_ip
  log "Installing one-shot nodeip rerun service at ${unit_path}"
  base_ip="${new_machine_network%%/*}"
  local hint_sed
  hint_sed="${base_ip//\//\\/}"

  cat >"$unit_path" <<UNIT
[Unit]
Description=SNO post-boot nodeip-configuration rerun
Wants=NetworkManager-wait-online.service
After=NetworkManager-wait-online.service nmstate-configuration.service nmstate.service firstboot-osupdate.target
Before=kubelet-dependencies.target ovs-configuration.service

[Service]
Type=oneshot
ExecStartPre=/usr/bin/bash -lc 'rm -f ${primary_ip_path} || true'
ExecStartPre=/usr/bin/bash -lc '\
  if [[ -f "${nodeip_defaults_path}" ]]; then \
    if grep -q "^KUBELET_NODEIP_HINT=" "${nodeip_defaults_path}"; then \
      sed -i "s/^KUBELET_NODEIP_HINT=.*/KUBELET_NODEIP_HINT=${hint_sed}/" "${nodeip_defaults_path}"; \
    else \
      echo "KUBELET_NODEIP_HINT=${base_ip}" >> "${nodeip_defaults_path}"; \
    fi; \
  else \
    echo "KUBELET_NODEIP_HINT=${base_ip}" > "${nodeip_defaults_path}"; \
  fi'
ExecStart=/usr/bin/systemctl restart nodeip-configuration.service
ExecStartPost=/usr/bin/systemctl restart wait-for-primary-ip.service
RemainAfterExit=no

[Install]
WantedBy=kubelet-dependencies.target
UNIT
  systemctl daemon-reload
  systemctl enable sno-nodeip-rerun.service
}

# Remove lingering nmstate state so new config applies after reboot
# Function: cleanup_nmstate_applied_files
# Purpose: Remove nmstate residual files so a new config applies cleanly.
cleanup_nmstate_applied_files() {
	local hn_fqdn hn_short
	hn_fqdn=$(hostname -f 2>/dev/null || hostname)
	hn_short=$(hostname -s 2>/dev/null || hostname)
	rm -f /etc/nmstate/openshift/applied || true
	rm -f "/etc/nmstate/${hn_short}.yml" "/etc/nmstate/${hn_fqdn}.yml" || true
	rm -f "/etc/nmstate/${hn_short}.applied" "/etc/nmstate/${hn_fqdn}.applied" || true
  log "Cleaned up nmstate residual state on node"
}

# Remove OVN certificate directories if present
# Function: remove_ovn_cert_folders
# Purpose: Remove OVN certificate directories if present.
remove_ovn_cert_folders() {
  local paths=(
    "${OVN_MULTUS_CERTS_DIR:-/etc/cni/multus/certs}"
    "${OVN_NODE_CERTS_DIR:-/var/lib/ovn-ic/etc/ovnkube-node-certs}"
  )
  for path in "${paths[@]}"; do
    if [[ -e "$path" ]]; then
      log "Removing OVN certificate directory: ${path}"
      rm -rf -- "$path" || true
    else
      log "OVN certificate directory not found (skipping): ${path}"
    fi
  done
  log "OVN certificate cleanup complete"
}
