#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export NODE_IP=$(get_main_ip)
export UI_PORT=${UI_PORT:-6008}
export UI_SERVICE_NAME=ocp-metal-ui
export NO_UI=${NO_UI:-n}

if [ "${NO_UI}" != "n" ]; then
    exit 0
fi

mkdir -p build

print_log "Starting ui"
skipper run "make -C assisted-service/ deploy-ui" ${SKIPPER_PARAMS} DEPLOY_TAG=${DEPLOY_TAG} DEPLOY_MANIFEST_PATH=${DEPLOY_MANIFEST_PATH} DEPLOY_MANIFEST_TAG=${DEPLOY_MANIFEST_TAG} NAMESPACE=${NAMESPACE}

print_log "Wait till ui api is ready"
wait_for_url_and_run "$(minikube service ${UI_SERVICE_NAME} -n ${NAMESPACE} --url)" "echo \"waiting for ${UI_SERVICE_NAME}\""

print_log "Starting port forwarding for deployment/${UI_SERVICE_NAME}"
wait_for_url_and_run "http://${NODE_IP}:${UI_PORT}" "spawn_port_forwarding_command ${UI_SERVICE_NAME} ${UI_PORT}"
print_log "OCP METAL UI can be reached at http://${NODE_IP}:${UI_PORT}"
print_log "Done"
