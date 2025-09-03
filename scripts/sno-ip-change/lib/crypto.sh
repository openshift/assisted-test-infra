#!/usr/bin/env bash

set -euo pipefail

collect_crypto_material() {
  local kubeconfig="$1"
  local output_json="$2"
  local crypto_dir="$3"
  local rule_files_dir="$4"

  need_cmd oc
  need_cmd jq
  need_cmd openssl
  need_cmd base64

  [[ -f "$kubeconfig" ]] || fail "kubeconfig not found: $kubeconfig"
  mkdir -p "$crypto_dir"

  # Admin kubeconfig client CA bundle
  oc --kubeconfig "$kubeconfig" -n openshift-config get cm admin-kubeconfig-client-ca -o jsonpath='{.data.ca-bundle\.crt}' \
    > "${crypto_dir}/admin-kubeconfig-client-ca.crt"

  # Kube-apiserver signer keys
  oc --kubeconfig "$kubeconfig" -n openshift-kube-apiserver-operator get secret loadbalancer-serving-signer -o jsonpath='{.data.tls\.key}' \
    | base64 -d > "${crypto_dir}/loadbalancer-serving-signer.key"
  oc --kubeconfig "$kubeconfig" -n openshift-kube-apiserver-operator get secret localhost-serving-signer -o jsonpath='{.data.tls\.key}' \
    | base64 -d > "${crypto_dir}/localhost-serving-signer.key"
  oc --kubeconfig "$kubeconfig" -n openshift-kube-apiserver-operator get secret service-network-serving-signer -o jsonpath='{.data.tls\.key}' \
    | base64 -d > "${crypto_dir}/service-network-serving-signer.key"

  # Ingress signer key and CN
  oc --kubeconfig "$kubeconfig" -n openshift-ingress-operator get secret router-ca -o jsonpath='{.data.tls\.key}' \
    | base64 -d > "${crypto_dir}/ingresskey-ingress-operator.key"

  local seed_ingress_crt_b64 seed_ingress_cn
  seed_ingress_crt_b64=$(oc --kubeconfig "$kubeconfig" -n openshift-ingress-operator get secret router-ca -o jsonpath='{.data.tls\.crt}')
  seed_ingress_cn=$(printf '%s' "$seed_ingress_crt_b64" | base64 -d \
    | openssl x509 -noout -subject -nameopt RFC2253 \
    | sed -n 's/^subject= *CN=\([^,]*\).*$/\1/p')

  # Build rules arrays
  local -a use_key_rules
  use_key_rules=(
    "kube-apiserver-lb-signer ${rule_files_dir}/loadbalancer-serving-signer.key"
    "kube-apiserver-localhost-signer ${rule_files_dir}/localhost-serving-signer.key"
    "kube-apiserver-service-network-signer ${rule_files_dir}/service-network-serving-signer.key"
  )
  if [[ -n "$seed_ingress_cn" ]]; then
    use_key_rules+=("${seed_ingress_cn} ${rule_files_dir}/ingresskey-ingress-operator.key")
  fi
  local -a use_cert_rules
  use_cert_rules=("${rule_files_dir}/admin-kubeconfig-client-ca.crt")

  # Emit JSON
  printf '%s\n' "${use_key_rules[@]}" | jq -R . | jq -s . > "${output_json}.keys.tmp"
  printf '%s\n' "${use_cert_rules[@]}" | jq -R . | jq -s . > "${output_json}.certs.tmp"
  jq -n \
    --argjson use_key_rules "$(cat "${output_json}.keys.tmp")" \
    --argjson use_cert_rules "$(cat "${output_json}.certs.tmp")" \
    '{ use_key_rules: $use_key_rules, use_cert_rules: $use_cert_rules }' \
    > "$output_json"
  rm -f "${output_json}.keys.tmp" "${output_json}.certs.tmp"
}

# Function: backup_seed_crypto
# Purpose: Backup key cluster crypto and kubeadmin password hash for safe restoration
# Parameters:
# - $1: kubeconfig path
# - $2: output directory (defaults to /var/tmp/backupCertsDir if empty)
backup_seed_crypto() {
  local kubeconfig="$1"
  local out_dir="${2:-/var/tmp/backupCertsDir}"

  need_cmd oc
  need_cmd base64
  [[ -f "$kubeconfig" ]] || fail "kubeconfig not found: $kubeconfig"

  umask 077
  mkdir -p "$out_dir"

  log "Backing up admin-kubeconfig-client-ca.crt to ${out_dir}"
  if ! oc --kubeconfig "$kubeconfig" get configmap admin-kubeconfig-client-ca -n openshift-config -o jsonpath='{.data.ca-bundle\.crt}' >"$out_dir/admin-kubeconfig-client-ca.crt"; then
    fail "Failed to read ConfigMap admin-kubeconfig-client-ca/ca-bundle.crt"
  fi
  chmod 600 "$out_dir/admin-kubeconfig-client-ca.crt" || true

  local name
  for name in loadbalancer-serving-signer localhost-serving-signer service-network-serving-signer; do
    log "Backing up ${name}.key to ${out_dir}"
    if ! oc --kubeconfig "$kubeconfig" get secret "$name" -n openshift-kube-apiserver-operator -o jsonpath='{.data.tls\.key}' 2>/dev/null | base64 -d >"$out_dir/${name}.key"; then
      fail "Failed to read Secret ${name} (tls.key) in openshift-kube-apiserver-operator"
    fi
    chmod 600 "$out_dir/${name}.key" || true
  done

  log "Backing up ingresskey-ingress-operator.key to ${out_dir}"
  if ! oc --kubeconfig "$kubeconfig" get secret router-ca -n openshift-ingress-operator -o jsonpath='{.data.tls\.key}' 2>/dev/null | base64 -d >"$out_dir/ingresskey-ingress-operator.key"; then
    fail "Failed to read Secret router-ca (tls.key) in openshift-ingress-operator"
  fi
  chmod 600 "$out_dir/ingresskey-ingress-operator.key" || true

  log "Backing up kubeadmin-password-hash.txt if present"
  local data
  if data=$(oc --kubeconfig "$kubeconfig" get secret kubeadmin -n kube-system -o jsonpath='{.data.kubeadmin}' 2>/dev/null || true); then
    if [[ -n "$data" ]]; then
      printf '%s' "$data" | base64 -d >"$out_dir/kubeadmin-password-hash.txt" || true
      chmod 600 "$out_dir/kubeadmin-password-hash.txt" || true
      log "kubeadmin-password-hash.txt written"
    else
      log "kubeadmin secret has no data.kubeadmin; skipping."
    fi
  else
    log "kubeadmin secret not found; skipping."
  fi

  log "Backup completed in $out_dir"
}

# Function: create_recert_config_file_for_seed_restoration
# Purpose: Create recert JSON config to restore original seed crypto from backup directory
# Parameters:
# - $1: backup dir (must contain backed up files)
# - $2: output config path (will be created)
create_recert_config_file_for_seed_restoration() {
  local backup_dir="$1"
  local config_path="$2"
  local restore_ip_value="${3:-}"
  local restore_machine_network_value="${4:-}"

  umask 077
  mkdir -p "$(dirname "$config_path")"

  local kubeadmin_hash
  local pw_file
  pw_file="$backup_dir/kubeadmin-password-hash.txt"
  if [[ -f "$pw_file" ]]; then
    kubeadmin_hash=$(cat "$pw_file")
  else
    kubeadmin_hash=""
  fi

  cat >"$config_path" <<JSON
{
  "dry_run": false,
  "extend_expiration": true,
  "etcd_endpoint": "localhost:2379",
  "summary_file_clean": "/kubernetes/recert-seed-restoration-summary.yaml",
  "crypto_dirs": ["/kubelet", "/kubernetes", "/machine-config-daemon"],
  "crypto_files": ["/host-etc/mcs-machine-config-content.json"],
  "cluster_customization_dirs": ["/kubelet", "/kubernetes", "/machine-config-daemon"],
  "cluster_customization_files": [
    "/host-etc/mcs-machine-config-content.json",
    "/host-etc/mco/proxy.env",
    "/host-etc/chrony.conf"
  ],
  "use_key_rules": [
    "kube-apiserver-lb-signer ${backup_dir}/loadbalancer-serving-signer.key",
    "kube-apiserver-localhost-signer ${backup_dir}/localhost-serving-signer.key",
    "kube-apiserver-service-network-signer ${backup_dir}/service-network-serving-signer.key",
    "ingresskey-ingress-operator ${backup_dir}/ingresskey-ingress-operator.key"
  ],
  "use_cert_rules": ["${backup_dir}/admin-kubeconfig-client-ca.crt"],
  "kubeadmin_password_hash": "${kubeadmin_hash}"
}
JSON
  chmod 600 "$config_path" || true

  # Optionally inject original IP and machine network CIDR(s) to support full rollback
  # Accept either a single value (string) or a JSON array (e.g. ["1.2.3.4","2001:db8::10"]).
  if [[ -n "$restore_ip_value" ]]; then
    if [[ "$restore_ip_value" == [* ]]; then
      jq --argjson ip "$restore_ip_value" '. + {ip: $ip}' "$config_path" >"${config_path}.tmp" && mv "${config_path}.tmp" "$config_path"
    else
      jq --arg ip "$restore_ip_value" '. + {ip: $ip}' "$config_path" >"${config_path}.tmp" && mv "${config_path}.tmp" "$config_path"
    fi
  fi

  if [[ -n "$restore_machine_network_value" ]]; then
    if [[ "$restore_machine_network_value" == [* ]]; then
      jq --argjson mn "$restore_machine_network_value" '. + {machine_network_cidr: $mn}' "$config_path" >"${config_path}.tmp" && mv "${config_path}.tmp" "$config_path"
    else
      jq --arg mn "$restore_machine_network_value" '. + {machine_network_cidr: $mn}' "$config_path" >"${config_path}.tmp" && mv "${config_path}.tmp" "$config_path"
    fi
  fi
}

# Function: restore_seed_crypto
# Purpose: Restore original seed crypto using recert and a temporary unauthenticated etcd
# Parameters:
# - $1: backup dir (default /var/tmp/backupCertsDir)
# - $2: recert image ref
# - $3: pull-secret path (optional; pass empty if not needed)
restore_seed_crypto() {
  local backup_dir="${1:-/var/tmp/backupCertsDir}"
  local recert_image="$2"
  local pull_secret_path="${3:-}"
  local restore_ip_value="${4:-}"
  local restore_machine_network_value="${5:-}"

  need_cmd podman
  need_cmd jq

  local etcd_pod_yaml="/etc/kubernetes/manifests/etcd-pod.yaml"
  [[ -f "$etcd_pod_yaml" ]] || fail "Missing $etcd_pod_yaml"

  # Validate required backup artifacts
  local required_files
  required_files=(
    "$backup_dir/admin-kubeconfig-client-ca.crt"
    "$backup_dir/loadbalancer-serving-signer.key"
    "$backup_dir/localhost-serving-signer.key"
    "$backup_dir/service-network-serving-signer.key"
    "$backup_dir/ingresskey-ingress-operator.key"
  )
  local f
  for f in "${required_files[@]}"; do
    [[ -f "$f" ]] || fail "Missing backup file: $f"
  done

  local cfg_path
  cfg_path="$backup_dir/recert_config.json"
  create_recert_config_file_for_seed_restoration "$backup_dir" "$cfg_path" "$restore_ip_value" "$restore_machine_network_value"

  # Start etcd and run recert with provided config
  run_etcd_container "${pull_secret_path}"
  log "Running recert to restore original seed crypto"
  podman rm -f recert >/dev/null 2>&1 || true
  podman run --pull=never --network=host --privileged --replace --name recert \
    -v /etc:/host-etc \
    -v /etc/ssh:/ssh \
    -v /etc/kubernetes:/kubernetes \
    -v /var/lib/kubelet/:/kubelet \
    -v /var/tmp:/var/tmp \
    -v /etc/machine-config-daemon:/machine-config-daemon \
    -v /etc/pki:/pki \
    -e RECERT_CONFIG="$cfg_path" \
    ${pull_secret_path:+--authfile "$pull_secret_path"} \
    "$recert_image"
  teardown_etcd
}
 