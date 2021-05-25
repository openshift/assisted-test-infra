#!/usr/bin/env bash

set -o nounset
set -o errexit
set -o pipefail
set -o xtrace

NAMESPACE=${NAMESPACE:-assisted-installer}
CLUSTER_ID=${CLUSTER_ID:-""}
ADDITIONAL_PARAMS=${ADDITIONAL_PARAMS:-""}
KUBECTL=${KUBECTL:-kubectl}
LOGS_DEST=${LOGS_DEST:-build}
KUBE_CRS=( clusterdeployment infraenv agentclusterinstall agent )

function download_service_logs() {
  mkdir -p ${LOGS_DEST} || true

  if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
    podman ps -a || true

    for service in "installer" "db"; do
      podman logs ${service} > ${LOGS_DEST}/onprem_${service}.log || true
    done
  else
    CRS=node,pod,svc,deployment,pv,pvc
    if [ ${ENABLE_KUBE_API} == "true"  ]; then
      collect_kube_api_resources
      CRS+=$(printf ",%s" "${KUBE_CRS[@]}")
    fi
    ${KUBECTL} cluster-info
    ${KUBECTL} get ${CRS} -n ${NAMESPACE} -o wide || true
    ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} logs {} -n ${NAMESPACE} --all-containers > ${LOGS_DEST}/k8s_{}.log" || true
    ${KUBECTL} get events -n ${NAMESPACE} --sort-by=.metadata.creationTimestamp > ${LOGS_DEST}/k8s_events.log || true
  fi
}

function download_cluster_logs() {
  if [ "${REMOTE_SERVICE_URL:-}" != '""' ]; then
    SERVICE_URL=${REMOTE_SERVICE_URL}
  else
    if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
      SERVICE_URL=http://localhost:8090
    else
      SERVICE_URL=$(KUBECONFIG=${HOME}/.kube/config minikube service assisted-service -n ${NAMESPACE} --url)
    fi
  fi

  skipper run ./discovery-infra/download_logs.py ${SERVICE_URL} ${LOGS_DEST} --cluster-id ${CLUSTER_ID} ${ADDITIONAL_PARAMS}
}

function collect_kube_api_resources() {
    for CR in "${KUBE_CRS[@]}"
    do
      ${KUBECTL} get ${CR} -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} get -ojson ${CR} {} -n ${NAMESPACE} > ${LOGS_DEST}/${CR}_{}.json" || true
    done
}


"$@"
