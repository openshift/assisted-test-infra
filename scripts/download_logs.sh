#!/usr/bin/env bash

set -o nounset
set -o errexit
set -o pipefail
set -o xtrace

NAMESPACE=${NAMESPACE:-assisted-installer}
PROFILE=${PROFILE:-minikube}
CLUSTER_ID=${CLUSTER_ID:-""}
ADDITIONAL_PARAMS=${ADDITIONAL_PARAMS:-""}
KUBECTL=${KUBECTL:-kubectl}
LOGS_DEST=${LOGS_DEST:-build}

function download_service_logs() {
  if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
    podman ps -a || true

    for service in "installer" "db"; do
        podman logs ${service} > ${LOGS_DEST}/onprem_${service}.log || true
    done    
  else
    ${KUBECTL} cluster-info
    ${KUBECTL} get pods -n ${NAMESPACE} || true

    for service in "assisted-service" "postgres" "scality" "createimage"; do
      ${KUBECTL} get pods -o=custom-columns=NAME:.metadata.name -A | grep ${service} | xargs -r -I {} sh -c "${KUBECTL} logs {} -n ${NAMESPACE} > ${LOGS_DEST}/k8s_{}.log" || true
    done
  fi
}

function download_cluster_logs() {
  if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
    SERVICE_URL=http://localhost:8090
  else
    SERVICE_URL=$(KUBECONFIG=${HOME}/.kube/config minikube service assisted-service -p ${PROFILE} -n ${NAMESPACE} --url)
  fi

  if [ "${REMOTE_SERVICE_URL:-}" != '""' ]; then
    SERVICE_URL=${REMOTE_SERVICE_URL}
  fi

  skipper run ./discovery-infra/download_logs.py ${SERVICE_URL} ${LOGS_DEST} --cluster-id ${CLUSTER_ID} ${ADDITIONAL_PARAMS}
}

"$@"
