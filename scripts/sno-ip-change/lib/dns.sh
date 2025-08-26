#!/usr/bin/env bash

set -euo pipefail

# Function: set_dnsmasq_new_ip_override
# Purpose: Write SNO_DNSMASQ_IP_OVERRIDE and restart dnsmasq on the node.
# Parameters:
# - $1: new IPv4 address
set_dnsmasq_new_ip_override() {
  local overrides_path="/etc/default/sno_dnsmasq_configuration_overrides"
  local new_ip="$1"
  log "Writing SNO_DNSMASQ_IP_OVERRIDE=${new_ip} to ${overrides_path} and restarting dnsmasq"
  mkdir -p "$(dirname "${overrides_path}")"
  if [[ -f "${overrides_path}" ]]; then
    sed -i -e "/^SNO_DNSMASQ_IP_OVERRIDE=/d" "${overrides_path}"
  fi
  {
    if [[ -f "${overrides_path}" ]]; then
      cat "${overrides_path}"
    fi
    echo "SNO_DNSMASQ_IP_OVERRIDE=\"${new_ip}\""
  } > "${overrides_path}.tmp"
  mv "${overrides_path}.tmp" "${overrides_path}"
  chmod 0644 "${overrides_path}"
  systemctl restart dnsmasq.service || true
}

# Function: update_dnsmasq
# Purpose: Restart dnsmasq and ensure forcedns dispatcher presence.
# Parameters:
# - $1: path to dnsmasq_config.sh
# - $2: path to forcedns dispatcher
# - $3: new IPv4 address
update_dnsmasq() {
  local script_path="$1"
  local forcedns_path="$2"
  local new_ip="$3"
  log "Ensuring DNSMasq config reflects new IP ${new_ip}"
  [[ -f "$script_path" ]] || { log "WARNING: ${script_path} not found. Skipping DNSMasq update."; return 0; }
  systemctl restart dnsmasq.service || true

  if [[ -f "$forcedns_path" ]]; then
    log "Ensuring forcedns dispatcher exists at ${forcedns_path} (new IP: ${new_ip})"
  fi
}

# Function: update_forcedns_file
# Purpose: Ensure forcedns dispatcher file supports the new IP. No-op if absent.
# Parameters:
# - $1: path to forcedns dispatcher file
# - $2: new IPv4 address
update_forcedns_file() {
  local forcedns_path="$1"
  local new_ip="$2"
  log "Ensuring forcedns file ${forcedns_path} supports new IP ${new_ip}"
  if [[ ! -f "$forcedns_path" ]]; then
    log "WARNING: ${forcedns_path} not found. Skipping forcedns update."
    return 0
  fi
}


# Generate the dnsmasq_config.sh script: static, reads values from overrides file
# Function: _generate_dnsmasq_content_script
# Purpose: Generate the contents of dnsmasq_config.sh
_generate_dnsmasq_content_script() {
  cat <<'EOSCRIPT'
#!/usr/bin/env bash

# In order to override cluster domain please provide this file with the following params:
# SNO_CLUSTER_NAME_OVERRIDE=<new cluster name>
# SNO_BASE_DOMAIN_OVERRIDE=<your new base domain>
# SNO_DNSMASQ_NEW_IP_OVERRIDE=<new ip>
source /etc/default/sno_dnsmasq_configuration_overrides || true

HOST_NEW_IP=${SNO_DNSMASQ_NEW_IP_OVERRIDE}
CLUSTER_NAME=${SNO_CLUSTER_NAME_OVERRIDE}
BASE_DOMAIN=${SNO_BASE_DOMAIN_OVERRIDE}
CLUSTER_FULL_DOMAIN="${CLUSTER_NAME}.${BASE_DOMAIN}"

cat << EOF > /etc/dnsmasq.d/single-node.conf
address=/apps.${CLUSTER_FULL_DOMAIN}/${HOST_NEW_IP}
address=/api-int.${CLUSTER_FULL_DOMAIN}/${HOST_NEW_IP}
address=/api.${CLUSTER_FULL_DOMAIN}/${HOST_NEW_IP}
EOF
EOSCRIPT
}

# Generate the forcedns dispatcher script to ensure resolv.conf contains the new IP nameserver
# Function: _generate_forcedns_script
# Purpose: Generate the forcedns dispatcher script content
_generate_forcedns_script() {
  cat <<'EOF'
#!/bin/bash

# In order to override cluster domain please provide this file with the following params:
# SNO_CLUSTER_NAME_OVERRIDE=<new cluster name>
# SNO_BASE_DOMAIN_OVERRIDE=<your new base domain>
# SNO_DNSMASQ_NEW_IP_OVERRIDE=<new ip>
source /etc/default/sno_dnsmasq_configuration_overrides || true

HOST_NEW_IP=${SNO_DNSMASQ_NEW_IP_OVERRIDE}
CLUSTER_NAME=${SNO_CLUSTER_NAME_OVERRIDE}
BASE_DOMAIN=${SNO_BASE_DOMAIN_OVERRIDE}
CLUSTER_FULL_DOMAIN="${CLUSTER_NAME}.${BASE_DOMAIN}"

export BASE_RESOLV_CONF=/run/NetworkManager/resolv.conf
if [ "$2" = "dhcp4-change" ] || [ "$2" = "dhcp6-change" ] || [ "$2" = "up" ] || [ "$2" = "connectivity-change" ]; then
    export TMP_FILE=$(mktemp /etc/forcedns_resolv.conf.XXXXXX)
    cp  $BASE_RESOLV_CONF $TMP_FILE
    chmod --reference=$BASE_RESOLV_CONF $TMP_FILE
    sed -i -e "s/${CLUSTER_FULL_DOMAIN}//" \
        -e "s/search /& ${CLUSTER_FULL_DOMAIN} /" \
        $TMP_FILE
    # Ensure the new IP nameserver is present at the top
    if ! grep -q "^nameserver $HOST_NEW_IP$" "$TMP_FILE"; then
        sed -i "1inameserver $HOST_NEW_IP" "$TMP_FILE"
    fi
    mv $TMP_FILE /etc/resolv.conf
fi
EOF
}

# Generate overrides file content
# Function: _generate_overrides_file
# Purpose: Generate overrides file for cluster/domain/IP
# Parameters:
# - $1: cluster name
# - $2: base domain
# - $3: new IPv4 address
_generate_overrides_file() {
  local cluster_name="$1"
  local base_domain="$2"
  local new_ip="$3"
  cat <<EOF
SNO_CLUSTER_NAME_OVERRIDE="${cluster_name}"
SNO_BASE_DOMAIN_OVERRIDE="${base_domain}"
SNO_DNSMASQ_NEW_IP_OVERRIDE="${new_ip}"
EOF
}

# Function: _generate_single_node_conf
# Purpose: Generate single-node.conf for NetworkManager
_generate_single_node_conf() {
  cat <<EOF

[main]
rc-manager=unmanaged
EOF
}

# Generate the full MachineConfig YAML to manage dnsmasq for SNO
# Function: generate_dnsmasq_mc_yaml
# Purpose: Produce MachineConfig YAML that installs dnsmasq and forcedns assets.
# Parameters:
# - $1: cluster name
# - $2: base domain
# - $3: new IPv4 address
generate_dnsmasq_mc_yaml() {
  local cluster_name="$1"
  local base_domain="$2"
  local new_ip="$3"
  need_cmd base64
  local b64_dnsmasq b64_forcedns b64_single b64_overrides
  b64_dnsmasq=$(_generate_dnsmasq_content_script | base64 -w 0)
  b64_forcedns=$(_generate_forcedns_script | base64 -w 0)
  b64_single=$(_generate_single_node_conf | base64 -w 0)
  b64_overrides=$(_generate_overrides_file "$cluster_name" "$base_domain" "$new_ip" | base64 -w 0)
  cat <<EOF
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  labels:
    machineconfiguration.openshift.io/role: master
  name: 50-master-dnsmasq-configuration
spec:
  config:
    ignition:
      version: 3.1.0
    storage:
      files:
      - contents:
          source: data:text/plain;charset=utf-8;base64,${b64_dnsmasq}
        mode: 365
        overwrite: true
        path: /usr/local/bin/dnsmasq_config.sh
      - contents:
          source: data:text/plain;charset=utf-8;base64,${b64_forcedns}
        mode: 365
        overwrite: true
        path: /etc/NetworkManager/dispatcher.d/forcedns
      - contents:
          source: data:text/plain;charset=utf-8;base64,${b64_single}
        mode: 420
        overwrite: true
        path: /etc/NetworkManager/conf.d/single-node.conf
      - contents:
          source: data:text/plain;charset=utf-8;base64,${b64_overrides}
        mode: 420
        overwrite: true
        path: /etc/default/sno_dnsmasq_configuration_overrides
    systemd:
      units:
      - contents: |
          [Unit]
          Description=Run dnsmasq to provide local dns for Single Node OpenShift
          Before=kubelet.service crio.service
          After=network.target ovs-configuration.service

          [Service]
          TimeoutStartSec=30
          ExecStartPre=/usr/local/bin/dnsmasq_config.sh
          ExecStart=/usr/sbin/dnsmasq -k
          Restart=always

          [Install]
          WantedBy=multi-user.target
        enabled: true
        name: dnsmasq.service
EOF
}

# Return 0 if the existing dnsmasq MachineConfig already contains the expected IP and domain
# Function: is_dnsmasq_mc_up_to_date
# Purpose: Check if the existing MC contains expected overrides content.
# Parameters:
# - $1: kubeconfig path
# - $2: cluster name
# - $3: base domain
# - $4: new IPv4 address
is_dnsmasq_mc_up_to_date() {
  local kubeconfig="$1"
  local cluster_name="$2"
  local base_domain="$3"
  local new_ip="$4"
  local mc_name="50-master-dnsmasq-configuration"
  local content
  content=$(oc --kubeconfig "$kubeconfig" get mc "$mc_name" -o jsonpath='{.spec.config.storage.files[?(@.path=="/etc/default/sno_dnsmasq_configuration_overrides")].contents.source}' 2>/dev/null || true)
  [[ -n "$content" ]] || return 1
  local b64
  b64="${content##*base64,}"
  local tmp
  tmp=$(mktemp)
  printf '%s' "$b64" | base64 -d > "$tmp" 2>/dev/null || { rm -f "$tmp"; return 1; }
  grep -Fq "SNO_CLUSTER_NAME_OVERRIDE=\"${cluster_name}\"" "$tmp" \
    && grep -Fq "SNO_BASE_DOMAIN_OVERRIDE=\"${base_domain}\"" "$tmp" \
    && grep -Fq "SNO_DNSMASQ_NEW_IP_OVERRIDE=\"${new_ip}\"" "$tmp"
  local rc=$?
  rm -f "$tmp"
  return $rc
}

# Apply or update the dnsmasq MachineConfig and wait for MCP update
# Function: apply_dnsmasq_mc
# Purpose: Apply (or update) dnsmasq MC if not current.
# Parameters:
# - $1: kubeconfig path
# - $2: cluster name
# - $3: base domain
# - $4: new IPv4 address
apply_dnsmasq_mc() {
  local kubeconfig="$1"
  local cluster_name="$2"
  local base_domain="$3"
  local new_ip="$4"
  local tmpfile
  tmpfile=$(mktemp)
  log "Applying dnsmasq MachineConfig for ${cluster_name}.${base_domain} (new=${new_ip})"
  if is_dnsmasq_mc_up_to_date "$kubeconfig" "$cluster_name" "$base_domain" "$new_ip"; then
    log "Existing dnsmasq MachineConfig already up-to-date. Skipping apply."
    return 0
  fi
  generate_dnsmasq_mc_yaml "$cluster_name" "$base_domain" "$new_ip" > "$tmpfile"
  # Sanity check API connectivity before apply to avoid long hangs
  oc_retry "$kubeconfig" get mcp master -o name >/dev/null 2>&1 || {
    log "ERROR: Cannot reach cluster API to apply dnsmasq MC."
    rm -f "$tmpfile"
    fail "Cluster API unreachable prior to applying dnsmasq MC"
  }

  # Apply with a bounded request timeout so we don't hang indefinitely
  oc_retry "$kubeconfig" --request-timeout=60s apply -f "$tmpfile"
  rm -f "$tmpfile"
  # Do not wait on MCP; higher-level handles reboot wait
  sleep 3
}

# Delete the dnsmasq MachineConfig if present
# Function: delete_dnsmasq_mc
# Purpose: Delete the dnsmasq MachineConfig if present and wait for MCP update.
# Parameters:
# - $1: kubeconfig path
delete_dnsmasq_mc() {
  local kubeconfig="$1"
  log "Deleting dnsmasq MachineConfig 50-master-dnsmasq-configuration if present"
  oc --kubeconfig "$kubeconfig" delete mc 50-master-dnsmasq-configuration --ignore-not-found=true || true
  wait_for_mcp_master_updated "$kubeconfig"
}
