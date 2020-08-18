#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
export SERVICE_NAME=assisted-service
export NAMESPACE=${NAMESPACE:-assisted-installer}
export SERVICE_URL=$(get_main_ip)
export SERVICE_PORT=${SERVICE_PORT:-6000}
export SERVICE_BASE_URL="http://${SERVICE_URL}:${SERVICE_PORT}"
export ENABLE_AUTH=${ENABLE_AUTH:-false}

mkdir -p build

print_log "Updating assisted_service params"
skipper run discovery-infra/update_assisted_service_cm.py ENABLE_AUTH=${ENABLE_AUTH}
skipper run "make -C assisted-service/ deploy-all" ${SKIPPER_PARAMS} DEPLOY_TAG=${DEPLOY_TAG} NAMESPACE=${NAMESPACE} ENABLE_AUTH=${ENABLE_AUTH}

print_log "Wait till ${SERVICE_NAME} api is ready"
wait_for_url_and_run "$(minikube service ${SERVICE_NAME} --url -n ${NAMESPACE})" "echo \"waiting for ${SERVICE_NAME}\""

print_log "Starting port forwarding for deployment/${SERVICE_NAME}"
wait_for_url_and_run ${SERVICE_BASE_URL} "spawn_port_forwarding_command ${SERVICE_NAME} ${SERVICE_PORT}"
print_log "${SERVICE_NAME} can be reached at ${SERVICE_BASE_URL} "
print_log "Done"
