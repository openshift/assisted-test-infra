#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export NODE_IP=$(get_main_ip)
export PROMETHEUS_SERVICE_NAME=prometheus-k8s
export NAMESPACE=${NAMESPACE:-assisted-installer}
export EXTERNAL_PORT=${EXTERNAL_PORT:-true}
export PROMETHEUS_UI_PORT=$(( 9091 + $NAMESPACE_INDEX ))
export OCP_PROMETHEUS_UI_PORT=$(( 9091 + $NAMESPACE_INDEX ))

if [[ ("${DEPLOY_TARGET}" != "minikube") ]]; then
    exit 0
fi

mkdir -p build

print_log "Wait till ui Prometheus Port is ready"
wait_for_url_and_run "$(minikube service ${PROMETHEUS_SERVICE_NAME} -n ${NAMESPACE} --url)" "echo \"waiting for ${PROMETHEUS_SERVICE_NAME}\""

add_firewalld_port $PROMETHEUS_UI_PORT

print_log "Starting port forwarding for deployment/${PROMETHEUS_SERVICE_NAME} on port $PROMETHEUS_UI_PORT"
wait_for_url_and_run "http://${NODE_IP}:${PROMETHEUS_UI_PORT}" "spawn_port_forwarding_command $PROMETHEUS_SERVICE_NAME $PROMETHEUS_UI_PORT $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube"
print_log "Prometheus UI can be reached at http://${NODE_IP}:${PROMETHEUS_UI_PORT}"

print_log "Done"
