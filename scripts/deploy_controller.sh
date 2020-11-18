#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export SERVICE_URL=$(get_main_ip)
export NAMESPACE=${NAMESPACE:-assisted-installer}
export SERVICE_PORT=$(( 6000 + $NAMESPACE_INDEX ))
export SERVICE_BASE_URL=${SERVICE_BASE_URL:-"http://${SERVICE_URL}:${SERVICE_PORT}"}

mkdir -p build

if [ "${DEPLOY_TARGET}" == "ocp" ]; then
    CLUSTER_ID=$(curl -s $SERVICE_BASE_URL/api/assisted-install/v1/clusters | jq -r '.[0] | .id')
    print_log "OCP cluster ID is $CLUSTER_ID"

    skipper run "scripts/ocp.sh deploy_controller $OCP_KUBECONFIG $SERVICE_BASE_URL $CLUSTER_ID $NAMESPACE $CONTROLLER_OCP"
fi
