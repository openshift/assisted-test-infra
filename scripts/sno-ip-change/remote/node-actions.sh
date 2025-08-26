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

OLD_IP=""
NEW_IP=""
NEW_MACHINE_NETWORK=""
INSTALL_CONFIG_PATH=""
PULL_SECRET_PATH=""
RECERT_IMAGE="quay.io/dmanor/recert:demo"
CRYPTO_JSON_PATH=""
CRYPTO_DIR_PATH=""
RECERT_CONFIG_PATH="$(mktemp)"
RECERT_CONTAINER_DATA_DIR_PATH=""
RECERT_IMAGE_ARCHIVE_PATH=""
PRIMARY_IP_PATH="/run/nodeip-configuration/primary-ip"
NODEIP_DEFAULTS_PATH="/etc/default/nodeip-configuration"
NODEIP_RERUN_UNIT_PATH="/etc/systemd/system/sno-nodeip-rerun.service"
# shellcheck disable=SC2034
OVN_MULTUS_CERTS_DIR="/etc/cni/multus/certs"
# shellcheck disable=SC2034
OVN_NODE_CERTS_DIR="/var/lib/ovn-ic/etc/ovnkube-node-certs"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--old-ip) OLD_IP="$2"; shift 2;;
		--new-ip) NEW_IP="$2"; shift 2;;
		--new-machine-network) NEW_MACHINE_NETWORK="$2"; shift 2;;
		--install-config) INSTALL_CONFIG_PATH="$2"; shift 2;;
		--pull-secret-path) PULL_SECRET_PATH="$2"; shift 2;;
		--recert-image) RECERT_IMAGE="$2"; shift 2;;
		--recert-container-data-dir-path) RECERT_CONTAINER_DATA_DIR_PATH="$2"; shift 2;;
		--crypto-json-path) CRYPTO_JSON_PATH="$2"; shift 2;;
		--crypto-dir-path) CRYPTO_DIR_PATH="$2"; shift 2;;
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

	[[ -n "$OLD_IP" ]] || fail "--old-ip is required"
	[[ -n "$NEW_IP" ]] || fail "--new-ip is required"
	[[ -n "$INSTALL_CONFIG_PATH" && -f "$INSTALL_CONFIG_PATH" ]] || fail "--install-config file missing"
	[[ -n "$PULL_SECRET_PATH" && -f "$PULL_SECRET_PATH" ]] || fail "--pull-secret file missing"
	[[ -n "$NEW_MACHINE_NETWORK" ]] || fail "--new-machine-network is required"
	[[ -n "$RECERT_IMAGE" ]] || fail "--recert-image is required"
	[[ -n "$RECERT_CONTAINER_DATA_DIR_PATH" ]] || fail "--recert-container-data-dir-path is required"
	[[ -n "$RECERT_IMAGE_ARCHIVE_PATH" && -f "$RECERT_IMAGE_ARCHIVE_PATH" ]] || fail "--recert-image-archive file missing"
	[[ -n "$CRYPTO_JSON_PATH" && -f "$CRYPTO_JSON_PATH" ]] || fail "--crypto-json-path file missing"
	[[ -n "$CRYPTO_DIR_PATH" && -d "$CRYPTO_DIR_PATH" ]] || fail "--crypto-dir-path directory missing"
	[[ -n "$PRIMARY_IP_PATH" ]] || fail "--primary-ip-path is required"
	[[ -n "$NODEIP_DEFAULTS_PATH" ]] || fail "--nodeip-defaults-path is required"
	[[ -n "$NODEIP_RERUN_UNIT_PATH" ]] || fail "--nodeip-rerun-unit-path is required"

	log "[node] Starting node-side actions for IP change"
	log "[node] Loading image archive from $RECERT_IMAGE_ARCHIVE_PATH"
	local load_output
	local loaded_ref
	if load_output=$(podman load -i "$RECERT_IMAGE_ARCHIVE_PATH" 2>&1); then
		loaded_ref=$(echo "$load_output" | awk '/Loaded image:/ {print $3; exit}')
		if [[ -n "$loaded_ref" ]]; then
			log "[node] Loaded image ref: $loaded_ref"
			if [[ "$loaded_ref" != "$RECERT_IMAGE" ]]; then
				log "[node] Tagging $loaded_ref as $RECERT_IMAGE"
				podman tag "$loaded_ref" "$RECERT_IMAGE" || true
			fi
		else
			log "[node] WARNING: Could not determine loaded image reference; assuming $RECERT_IMAGE is available"
		fi
	else
		log "[node] ERROR: Failed to load image archive: $load_output"
		return 1
	fi
	
	ensure_cluster_is_down
	run_etcd_container "$PULL_SECRET_PATH"
	run_recert \
		"$RECERT_CONFIG_PATH" \
		"$INSTALL_CONFIG_PATH" \
		"$PULL_SECRET_PATH" \
		"$RECERT_IMAGE" \
		"$RECERT_CONTAINER_DATA_DIR_PATH" \
		"$OLD_IP" \
		"$NEW_IP" \
		"$NEW_MACHINE_NETWORK" \
		"$CRYPTO_JSON_PATH" \
		"$CRYPTO_DIR_PATH"
	teardown_etcd
	ensure_nmstate_configuration_enabled
	ensure_kubelet_enabled
	ensure_nodeip_rerun_service "$PRIMARY_IP_PATH" "$NODEIP_DEFAULTS_PATH" "$NEW_MACHINE_NETWORK" "$NODEIP_RERUN_UNIT_PATH"
	set_dnsmasq_new_ip_override "$NEW_IP"
	cleanup_nmstate_applied_files
	remove_ovn_cert_folders
	reboot_node
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
	main "$@"
fi
