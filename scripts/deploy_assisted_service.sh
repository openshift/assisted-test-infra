#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export SERVICE_NAME=assisted-service
export SERVICE_URL=$(get_main_ip)
export ENABLE_AUTH=${ENABLE_AUTH:-false}
export NAMESPACE=${NAMESPACE:-assisted-installer}
export SERVICE_PORT=$(( 6000 + $NAMESPACE_INDEX ))
export SERVICE_BASE_URL="http://${SERVICE_URL}:${SERVICE_PORT}"
export EXTERNAL_PORT=${EXTERNAL_PORT:-y}
export PROFILE=${PROFILE:-assisted-installer}

mkdir -p build

print_log "Updating assisted_service params"
skipper run discovery-infra/update_assisted_service_cm.py ENABLE_AUTH=${ENABLE_AUTH}
skipper run "make -C assisted-service/ deploy-all" ${SKIPPER_PARAMS} DEPLOY_TAG=${DEPLOY_TAG} DEPLOY_MANIFEST_PATH=${DEPLOY_MANIFEST_PATH} DEPLOY_MANIFEST_TAG=${DEPLOY_MANIFEST_TAG} NAMESPACE=${NAMESPACE} ENABLE_AUTH=${ENABLE_AUTH} PROFILE=${PROFILE}

print_log "Wait till ${SERVICE_NAME} api is ready"
wait_for_url_and_run "$(minikube service ${SERVICE_NAME} --url -p $PROFILE -n ${NAMESPACE})" "echo \"waiting for ${SERVICE_NAME}\""

add_firewalld_port $SERVICE_PORT

print_log "Starting port forwarding for deployment/${SERVICE_NAME} on port $SERVICE_PORT"
wait_for_url_and_run ${SERVICE_BASE_URL} "spawn_port_forwarding_command $SERVICE_NAME $SERVICE_PORT $NAMESPACE $NAMESPACE_INDEX $PROFILE"
print_log "${SERVICE_NAME} can be reached at ${SERVICE_BASE_URL} "
print_log "Done"
