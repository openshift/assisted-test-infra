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
 