#!/usr/bin/env bash

set -euo pipefail


# Function: fetch_install_config
# Purpose: Fetch install-config from cluster-config-v1 CM and write to path.
# Parameters:
# - $1: output path to write install-config YAML
# - $2: kubeconfig path
fetch_install_config() {
  local out_path="$1"
  local kubeconfig="$2"
  log "Fetching install-config to ${out_path}"
  [[ -f "$kubeconfig" ]] || fail "kubeconfig not found: $kubeconfig"
  oc get cm -n kube-system cluster-config-v1 -o json --kubeconfig "$kubeconfig" \
    | jq -r '.data."install-config"' \
    | sed 's/^/  /' \
    | tee "$out_path" >/dev/null
  [[ -s "$out_path" ]] || fail "Failed to write install-config to $out_path"
}

# Ensure cluster node services are down (declarative)
# Function: ensure_cluster_is_down
# Purpose: Stop/disable kubelet and stop crio containers/services.
ensure_cluster_is_down() {
  log "Ensuring cluster services are down (kubelet, crio)"
  if systemctl is-active --quiet kubelet.service; then
    systemctl stop kubelet.service || true
  fi
  if systemctl is-enabled --quiet kubelet.service; then
    systemctl disable kubelet.service || true
  fi
  local pids
  if systemctl is-active --quiet crio.service; then
    pids=$(crictl ps -q || true)
  else
    pids=""
  fi
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs --no-run-if-empty --max-args 1 --max-procs 10 crictl stop --timeout 5 || true
  fi
  if systemctl is-active --quiet crio.service; then
    systemctl stop crio.service || true
  fi
}


# Function: run_etcd_container
# Purpose: Start a non-auth etcd container with data-dir mounted for recert.
# Parameters:
# - $1: pull-secret path for image auth
run_etcd_container() {
  local pull_secret_path="$1"
  log "Starting unauthenticated etcd container"
  local etcd_pod_yaml="/etc/kubernetes/manifests/etcd-pod.yaml"
  [[ -f "$etcd_pod_yaml" ]] || fail "Missing $etcd_pod_yaml"
  local ETCD_IMAGE
  ETCD_IMAGE=$(jq -r '.spec.containers[] | select(.name=="etcd") | .image' "$etcd_pod_yaml")
  [[ -n "$ETCD_IMAGE" && "$ETCD_IMAGE" != "null" ]] || fail "Failed to parse etcd image from $etcd_pod_yaml"
  podman rm -f etcd-nonauth >/dev/null 2>&1 || true
  podman run --authfile "$pull_secret_path" --network=host --privileged --replace --detach --name etcd-nonauth -v /var/lib/etcd:/store --entrypoint etcd "$ETCD_IMAGE" --name editor --data-dir /store
  sleep 3
  if ! podman ps --format '{{.Names}}' | grep -q '^etcd-nonauth$'; then
    fail "etcd-nonauth container failed to start"
  fi
}

# Function: run_recert
# Purpose: Prepare recert config and run the recert container with volumes.
# Parameters:
# - $1: recert config path (output)
# - $2: install-config path
# - $3: pull-secret path
# - $4: recert image
# - $5: recert container data dir path (inside container)
# - $6: old IP
# - $7: new IP
# - $8: new machine network CIDR
# - $9: crypto rules JSON path (optional)
# - $10: crypto rules directory path (optional)
run_recert() {
  local recert_cfg_path="$1"
  local install_cfg_path="$2"
  local pull_secret_path="$3"
  local recert_image="$4"
  local recert_container_data_dir_path="$5"
  local old_ip="$6"
  local new_ip="$7"
  local new_machine_network="$8"
  local crypto_json="${9:-}"
  local crypto_dir="${10:-}"
  log "Preparing recert config at ${recert_cfg_path}"
  mkdir -p "$(dirname "$recert_cfg_path")"
  cat >"$recert_cfg_path" <<EOF
etcd_endpoint: localhost:2379
ip: ${new_ip}
machine_network_cidr: ${new_machine_network}
summary_file_clean: /var/tmp/recert-summary.yaml
crypto_dirs:
- /kubelet
- /kubernetes
- /machine-config-daemon
crypto_files:
- /host-etc/mcs-machine-config-content.json
cluster_customization_dirs:
- /kubelet
- /kubernetes
- /machine-config-daemon
cluster_customization_files:
- /host-etc/mcs-machine-config-content.json
- /host-etc/mco/proxy.env	
- /host-etc/chrony.conf
cn_san_replace_rules:
- ${old_ip},${new_ip}
extend_expiration: true
install_config: |
$(cat "$install_cfg_path")
EOF
  if [[ -n "$crypto_json" && -f "$crypto_json" ]]; then
    log "Including crypto rules from ${crypto_json}"
    {
      echo "use_key_rules:"
      jq -r '.use_key_rules[] | "- \"" + . + "\""' "$crypto_json"
      echo "use_cert_rules:"
      jq -r '.use_cert_rules[] | "- \"" + . + "\""' "$crypto_json"
    } >>"$recert_cfg_path"
  fi
  [[ -s "$recert_cfg_path" ]] || fail "Failed to write recert config"
  log "Running recert container ${recert_image}"
  podman rm -f recert >/dev/null 2>&1 || true
  podman run --pull=never --network=host --privileged --replace --name recert \
    -v /etc:/host-etc \
    -v /etc/ssh:/ssh \
    -v /etc/kubernetes:/kubernetes \
    -v /var/lib/kubelet/:/kubelet \
    -v /var/tmp:/var/tmp \
    -v /etc/machine-config-daemon:/machine-config-daemon \
    -v /etc/pki:/pki \
    -v "${crypto_dir}":"${recert_container_data_dir_path}" \
    -v "${recert_cfg_path}":"${recert_container_data_dir_path}"/recert-config.yaml \
    -e RECERT_CONFIG="${recert_container_data_dir_path}"/recert-config.yaml \
    --authfile "$pull_secret_path"  "$recert_image"
}

# Function: run_recert_dual
# Purpose: Prepare recert config with lists for ip and machine_network_cidr and run the recert container.
# Parameters:
# - $1: recert config path (output)
# - $2: install-config path
# - $3: pull-secret path
# - $4: recert image
# - $5: recert container data dir path (inside container)
# - $6: old IPv4
# - $7: new IPv4
# - $8: new IPv6
# - $9: old IPv6
# - $10: IPv4 machine network CIDR
# - $11: IPv6 machine network CIDR
# - $12: crypto rules JSON path (optional)
# - $13: crypto rules directory path (optional)
run_recert_dual() {
  local recert_cfg_path="$1"
  local install_cfg_path="$2"
  local pull_secret_path="$3"
  local recert_image="$4"
  local recert_container_data_dir_path="$5"
  local old_ipv4="$6"
  local new_ipv4="$7"
  local new_ipv6="$8"
  local old_ipv6="$9"
  local cidr_v4="${10}"
  local cidr_v6="${11}"
  local crypto_json="${12:-}"
  local crypto_dir="${13:-}"
  log "Preparing dual-stack recert config at ${recert_cfg_path}"
  mkdir -p "$(dirname "$recert_cfg_path")"
  cat >"$recert_cfg_path" <<EOF
etcd_endpoint: localhost:2379
ip:
- ${new_ipv4}
- ${new_ipv6}
machine_network_cidr:
- ${cidr_v4}
- ${cidr_v6}
summary_file_clean: /var/tmp/recert-summary.yaml
crypto_dirs:
- /kubelet
- /kubernetes
- /machine-config-daemon
crypto_files:
- /host-etc/mcs-machine-config-content.json
cluster_customization_dirs:
- /kubelet
- /kubernetes
- /machine-config-daemon
cluster_customization_files:
- /host-etc/mcs-machine-config-content.json
- /host-etc/mco/proxy.env	
- /host-etc/chrony.conf
cn_san_replace_rules:
- ${old_ipv4},${new_ipv4}
- ${old_ipv6},${new_ipv6}
extend_expiration: true
install_config: |
$(cat "$install_cfg_path")
EOF
  if [[ -n "$crypto_json" && -f "$crypto_json" ]]; then
    log "Including crypto rules from ${crypto_json}"
    {
      echo "use_key_rules:"
      jq -r '.use_key_rules[] | "- \"" + . + "\""' "$crypto_json"
      echo "use_cert_rules:"
      jq -r '.use_cert_rules[] | "- \"" + . + "\""' "$crypto_json"
    } >>"$recert_cfg_path"
  fi
  [[ -s "$recert_cfg_path" ]] || fail "Failed to write recert config"
  log "Running recert container ${recert_image} (dual-stack)"
  podman rm -f recert >/dev/null 2>&1 || true
  podman run --pull=never --network=host --privileged --replace --name recert \
    -v /etc:/host-etc \
    -v /etc/ssh:/ssh \
    -v /etc/kubernetes:/kubernetes \
    -v /var/lib/kubelet/:/kubelet \
    -v /var/tmp:/var/tmp \
    -v /etc/machine-config-daemon:/machine-config-daemon \
    -v /etc/pki:/pki \
    -v "${crypto_dir}":"${recert_container_data_dir_path}" \
    -v "${recert_cfg_path}":"${recert_container_data_dir_path}"/recert-config.yaml \
    -e RECERT_CONFIG="${recert_container_data_dir_path}"/recert-config.yaml \
    --authfile "$pull_secret_path"  "$recert_image"
}

# Function: teardown_etcd
# Purpose: Remove the temporary etcd container used during recert.
teardown_etcd() {
  log "Tearing down etcd-nonauth container"
  podman rm -f etcd-nonauth >/dev/null 2>&1 || true
}
