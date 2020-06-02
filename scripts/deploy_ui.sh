#!/usr/bin/env bash
set -euxo pipefail

source scripts/utils.sh

export NODE_IP=$(get_main_ip)
export UI_PORT=${UI_PORT:-6008}
export UI_INTERNAL_PORT=8080
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
export CONTAINER_COMMAND=${CONTAINER_COMMAND:-podman}
export UI_DEPLOY_FILE=build/ui_deploy.yaml
export UI_SERVICE_NAME=ocp-metal-ui

mkdir -p build

echo "Starting ui"
${CONTAINER_COMMAND} run --pull=always --rm quay.io/ocpmetal/ocp-metal-ui:latest /deploy/deploy_config.sh -i quay.io/ocpmetal/ocp-metal-ui:latest > ${UI_DEPLOY_FILE}
kubectl --kubeconfig=${KUBECONFIG} apply -f ${UI_DEPLOY_FILE}

echo "Config firewalld"
sudo systemctl start firewalld
sudo firewall-cmd --zone=public --permanent --add-port=${UI_PORT}/tcp
sudo firewall-cmd --reload

echo "wait till ui api is ready"
wait_for_url_and_run "$(minikube service ${UI_SERVICE_NAME} --url -n assisted-installer)" "echo \"waiting for ${UI_SERVICE_NAME}\""

echo "starting port forwarding for deployment/${UI_SERVICE_NAME}"

wait_for_url_and_run "http://${NODE_IP}:${UI_PORT}" "spawn_port_forwarding_command ${UI_PORT} ${UI_INTERNAL_PORT} ${UI_SERVICE_NAME}"

echo "OCP METAL UI can be reached at http://${NODE_IP}:${UI_PORT}"

echo "Done"
