#!/usr/bin/env bash
set -euxo pipefail

source scripts/utils.sh
export INVENTORY_URL=$(get_main_ip)
export INVENTORY_PORT=${INVENTORY_PORT:-6000}
export INVENTORY_INTERNAL_PORT=8090
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
export SERVICE_NAME=bm-inventory

echo "Config firewalld"
sudo systemctl start firewalld
sudo firewall-cmd --zone=public --permanent --add-port=${INVENTORY_PORT}/tcp
sudo firewall-cmd --zone=libvirt --permanent --add-port=${INVENTORY_PORT}/tcp
sudo firewall-cmd --reload

echo "Starting make run, will start ${SERVICE_NAME}"
make run

echo "Rollout ${SERVICE_NAME}"
kubectl rollout restart deployment/${SERVICE_NAME} -n assisted-installer

echo "wait till ${SERVICE_NAME} api is ready"
wait_for_url_and_run "$(minikube service ${SERVICE_NAME} --url -n assisted-installer)" "echo \"waiting for ${SERVICE_NAME}\""

echo "starting port forwarding for deployment/${SERVICE_NAME}"

wait_for_url_and_run "http://${INVENTORY_URL}:${INVENTORY_PORT}" "spawn_port_forwarding_command ${INVENTORY_PORT} ${INVENTORY_INTERNAL_PORT} ${SERVICE_NAME}"

echo "${SERVICE_NAME} can be reached at http://${INVENTORY_URL}:${INVENTORY_PORT} "

echo "Done"
