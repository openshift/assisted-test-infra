#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export UI_SERVICE_NAME=assisted-installer-ui
export NO_UI=${NO_UI:-n}
export NAMESPACE=${NAMESPACE:-assisted-installer}
export EXTERNAL_PORT=${EXTERNAL_PORT:-true}

if [[ "${NO_UI}" != "n" ]] || [[ "${DEPLOY_TARGET}" != @(minikube|kind) ]]; then
    exit 0
fi

mkdir -p build

print_log "Starting ui"
skipper run "make -C assisted-service/ deploy-ui" ${SKIPPER_PARAMS} TARGET=${DEPLOY_TARGET} DEPLOY_TAG=${DEPLOY_TAG} DEPLOY_MANIFEST_PATH=${DEPLOY_MANIFEST_PATH} DEPLOY_MANIFEST_TAG=${DEPLOY_MANIFEST_TAG} NAMESPACE=${NAMESPACE}

case ${DEPLOY_TARGET} in
    minikube)
        node_ip=$(get_main_ip)
        ui_port=$(( 6008 + $NAMESPACE_INDEX ))
        ui_url="$(minikube service ${UI_SERVICE_NAME} -n ${NAMESPACE} --url)"
        ;;

    kind)
        EXTERNAL_PORT=false
        node_ip=$(hostname)
        ui_port=80
        ui_url="http://${node_ip}/"
        ;;
    *)
        echo "Non-supported deploy target ${DEPLOY_TARGET}!";
        exit 1
        ;;
esac

print_log "Wait till UI is ready"
wait_for_url_and_run ${ui_url} "echo \"waiting for ${ui_url}\""

add_firewalld_port $ui_port

if [[ "${DEPLOY_TARGET}" == "minikube" ]]; then
    print_log "Starting port forwarding for deployment/${UI_SERVICE_NAME} on port $ui_port"
    wait_for_url_and_run "http://${node_ip}:${ui_port}" "spawn_port_forwarding_command $UI_SERVICE_NAME $ui_port $NAMESPACE $NAMESPACE_INDEX $KUBECONFIG minikube"
fi

print_log "Done. Assisted-installer UI can be reached at http://${node_ip}:${ui_port}"
