#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC1091

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
# shellcheck source=../lib/util.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/util.sh"
# shellcheck source=../lib/network.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/network.sh"
# shellcheck source=../lib/recert.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/recert.sh"
# shellcheck source=../lib/dns.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/dns.sh"
# shellcheck source=../lib/crypto.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/crypto.sh"
# shellcheck source=../lib/cluster.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/cluster.sh"
# shellcheck source=../lib/mc.sh
# shellcheck disable=SC1091
. "${SCRIPT_DIR}/lib/mc.sh"

OLD_IP=""
NEW_IP=""
NEW_MACHINE_NETWORK=""
RECERT_IMAGE="quay.io/dmanor/recert:demo"
RECERT_CONFIG_PATH="$(mktemp)"
RECERT_CONTAINER_DATA_DIR_PATH="/data"
RECERT_IMAGE_ARCHIVE_PATH=""
PRIMARY_IP_PATH="/run/nodeip-configuration/primary-ip"
NODEIP_DEFAULTS_PATH="/etc/default/nodeip-configuration"
NODEIP_RERUN_UNIT_PATH="/etc/systemd/system/sno-nodeip-rerun.service"
# shellcheck disable=SC2034
OVN_MULTUS_CERTS_DIR="/etc/cni/multus/certs"
# shellcheck disable=SC2034
OVN_NODE_CERTS_DIR="/var/lib/ovn-ic/etc/ovnkube-node-certs"
KUBECONFIG_INTERNAL_PATH="/etc/kubernetes/static-pod-resources/kube-apiserver-certs/secrets/node-kubeconfigs/lb-ext.kubeconfig"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--old-ip) OLD_IP="$2"; shift 2;;
		--new-ip) NEW_IP="$2"; shift 2;;
		--new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
		--recert-image) RECERT_IMAGE="$2"; shift 2;;
		--recert-container-data-dir-path) RECERT_CONTAINER_DATA_DIR_PATH="$2"; shift 2;;
		--primary-ip-path) PRIMARY_IP_PATH="$2"; shift 2;;
		--nodeip-defaults-path) NODEIP_DEFAULTS_PATH="$2"; shift 2;;
		--nodeip-rerun-unit-path) NODEIP_RERUN_UNIT_PATH="$2"; shift 2;;
		--recert-image-archive) RECERT_IMAGE_ARCHIVE_PATH="$2"; shift 2;;
		*) fail "Unknown argument: $1";;
	esac
done

main() {
	require_root
	need_cmd sed
	need_cmd jq
	need_cmd podman
	need_cmd crictl
	need_cmd systemctl
	need_cmd base64
	need_cmd oc

	[[ -n "$OLD_IP" ]] || fail "--old-ip is required"
	[[ -n "$NEW_IP" ]] || fail "--new-ip is required"
	[[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required"
	[[ -n "$RECERT_IMAGE" ]] || fail "--recert-image is required"
	[[ -n "$RECERT_CONTAINER_DATA_DIR_PATH" ]] || fail "--recert-container-data-dir-path is required"
	[[ -n "$RECERT_IMAGE_ARCHIVE_PATH" && -f "$RECERT_IMAGE_ARCHIVE_PATH" ]] || fail "--recert-image-archive file missing"
	[[ -f "$KUBECONFIG_INTERNAL_PATH" ]] || fail "Internal kubeconfig not found at $KUBECONFIG_INTERNAL_PATH"

	log "Starting node-side actions for IP change (single-stack)"
	log "Loading image archive from $RECERT_IMAGE_ARCHIVE_PATH"
	local load_output
	local loaded_ref
	if load_output=$(podman load -i "$RECERT_IMAGE_ARCHIVE_PATH" 2>&1); then
		loaded_ref=$(echo "$load_output" | awk '/Loaded image:/ {print $3; exit}')
		if [[ -n "$loaded_ref" ]]; then
			log "Loaded image ref: $loaded_ref"
			if [[ "$loaded_ref" != "$RECERT_IMAGE" ]]; then
				log "Tagging $loaded_ref as $RECERT_IMAGE"
				podman tag "$loaded_ref" "$RECERT_IMAGE" || true
			fi
		else
			fail "Could not determine loaded image reference from archive load output"
		fi
	else
		log "ERROR: Failed to load image archive: $load_output"
		return 1
	fi

	local iface nmstate_tmp prefix
	iface=$(detect_br_ex_interface || true)
	[[ -n "$iface" ]] || fail "Failed to auto-detect interface attached to br-ex or connected ethernet on node"
	prefix="${NEW_MACHINE_NETWORK##*/}"
	nmstate_tmp=$(create_nmstate_tmp_file "$iface" "$NEW_IP" "$prefix")
	oc --kubeconfig "$KUBECONFIG_INTERNAL_PATH" get mcp master >/dev/null 2>&1 || fail "Internal API is not reachable via $KUBECONFIG_INTERNAL_PATH"
	log "Applying single-stack nmstate MachineConfig via internal kubeconfig"
	if is_nmstate_mc_up_to_date "$nmstate_tmp" "$KUBECONFIG_INTERNAL_PATH"; then
		log "nmstate MachineConfig already up-to-date; skipping apply"
	else
		apply_nmstate_mc "$nmstate_tmp" "$KUBECONFIG_INTERNAL_PATH"
		wait_for_mcp_master_updated "$KUBECONFIG_INTERNAL_PATH"
		wait_for_node_config_contains_mc "$KUBECONFIG_INTERNAL_PATH" "nmstate MC"
	fi

	local install_cfg
	install_cfg=$(mktemp)
	fetch_install_config "$install_cfg" "$KUBECONFIG_INTERNAL_PATH"

	local crypto_dir crypto_json
	crypto_dir=$(mktemp -d)
	crypto_json=$(mktemp)
	collect_crypto_material "$KUBECONFIG_INTERNAL_PATH" "$crypto_json" "$crypto_dir" "/data"

	ensure_cluster_is_down
	run_etcd_container ""
	run_recert \
		"$RECERT_CONFIG_PATH" \
		"$install_cfg" \
		"" \
		"$RECERT_IMAGE" \
		"$RECERT_CONTAINER_DATA_DIR_PATH" \
		"$OLD_IP" \
		"$NEW_IP" \
		"$NEW_MACHINE_NETWORK" \
		"$crypto_json" \
		"$crypto_dir"
	teardown_etcd
	ensure_nmstate_configuration_enabled
	ensure_kubelet_enabled
	ensure_nodeip_rerun_service "$PRIMARY_IP_PATH" "$NODEIP_DEFAULTS_PATH" "$NEW_MACHINE_NETWORK" "$NODEIP_RERUN_UNIT_PATH"
	set_dnsmasq_new_ip_override "$NEW_IP"
	cleanup_nmstate_applied_files
	remove_ovn_cert_folders
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
	main "$@"
fi
