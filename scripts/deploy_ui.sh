#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export NODE_IP=$(get_main_ip)
export UI_SERVICE_NAME=ocp-metal-ui
export NO_UI=${NO_UI:-n}
export NAMESPACE=${NAMESPACE:-assisted-installer}
export EXTERNAL_PORT=${EXTERNAL_PORT:-y}
export UI_PORT=$(( 6008 + $NAMESPACE_INDEX ))
export OCP_UI_PORT=$(( 7008 + $NAMESPACE_INDEX ))

if [[ "${NO_UI}" != "n" || ("${DEPLOY_TARGET}" != "minikube" && "${DEPLOY_TARGET}" != "ocp") ]]; then
    exit 0
fi

mkdir -p build

print_log "Starting ui"
if [ "${DEPLOY_TARGET}" == "minikube" ]; then
    skipper run "make -C assisted-service/ deploy-ui" ${SKIPPER_PARAMS} DEPLOY_TAG=${DEPLOY_TAG} DEPLOY_MANIFEST_PATH=${DEPLOY_MANIFEST_PATH} DEPLOY_MANIFEST_TAG=${DEPLOY_MANIFEST_TAG} NAMESPACE=${NAMESPACE}

    print_log "Wait till ui api is ready"
    wait_for_url_and_run "$(minikube service ${UI_SERVICE_NAME} -n ${NAMESPACE} --url)" "echo \"waiting for ${UI_SERVICE_NAME}\""

    add_firewalld_port $UI_PORT

    print_log "Starting port forwarding for deployment/${UI_SERVICE_NAME} on port $UI_PORT"
    wait_for_url_and_run "http://${NODE_IP}:${UI_PORT}" "spawn_port_forwarding_command $UI_SERVICE_NAME $UI_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube"
    print_log "OCP METAL UI can be reached at http://${NODE_IP}:${UI_PORT}"
elif [ "${DEPLOY_TARGET}" == "ocp" ]; then
    IP_NODEPORT=$(skipper run "scripts/ocp.sh deploy_ui $OCP_KUBECONFIG $UI_SERVICE_NAME $NAMESPACE" 2>&1 | tee /dev/tty | tail -1)
    read -r CLUSTER_VIP SERVICE_NODEPORT <<< "$IP_NODEPORT"

    add_firewalld_port $OCP_UI_PORT

    CLUSTER_UI_URL=http://${NODE_IP}:${OCP_UI_PORT}
    wait_for_url_and_run "${CLUSTER_UI_URL}" "spawn_port_forwarding_command $UI_SERVICE_NAME $OCP_UI_PORT $NAMESPACE $NAMESPACE_INDEX $OCP_KUBECONFIG ocp ${CLUSTER_VIP} ${SERVICE_NODEPORT}"
    print_log "OCP METAL UI can be reached at ${CLUSTER_UI_URL}"
fi

print_log "Done"
