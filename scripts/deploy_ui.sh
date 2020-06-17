#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export NODE_IP=$(get_main_ip)
export UI_PORT=${UI_PORT:-6008}
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
export CONTAINER_COMMAND=${CONTAINER_COMMAND:-podman}
export UI_DEPLOY_FILE=build/ui_deploy.yaml
export UI_SERVICE_NAME=ocp-metal-ui

mkdir -p build
#In case deploy tag is empty use latest
[[ -z "${DEPLOY_TAG}" ]] && export DEPLOY_TAG=latest 

print_log "Starting ui"
${CONTAINER_COMMAND} run --pull=always --rm quay.io/ocpmetal/ocp-metal-ui:${DEPLOY_TAG} /deploy/deploy_config.sh -i quay.io/ocpmetal/ocp-metal-ui:${DEPLOY_TAG} > ${UI_DEPLOY_FILE}
kubectl --kubeconfig=${KUBECONFIG} apply -f ${UI_DEPLOY_FILE}

print_log "Config firewall"
sudo systemctl start firewalld
sudo firewall-cmd --zone=public --permanent --add-port=${UI_PORT}/tcp
sudo firewall-cmd --reload

print_log "Wait till ui api is ready"
wait_for_url_and_run "$(minikube service ${UI_SERVICE_NAME} --url -n assisted-installer)" "echo \"waiting for ${UI_SERVICE_NAME}\""

print_log "Starting port forwarding for deployment/${UI_SERVICE_NAME}"

wait_for_url_and_run "http://${NODE_IP}:${UI_PORT}" "spawn_port_forwarding_command ${UI_SERVICE_NAME} ${UI_PORT}"

print_log "OCP METAL UI can be reached at http://${NODE_IP}:${UI_PORT}"
print_log "Done"
