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
JUNIT_REPORT_DIR=${JUNIT_REPORT_DIR:-"reports/"}
KUBE_CRS=(clusterdeployment infraenv agentclusterinstall agent)
CAPI_PROVIDER_CRS=(agentmachine agentcluster)

function download_service_logs() {
  mkdir -p ${LOGS_DEST} || true

  if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
    podman ps -a || true

    for service in "assisted-service" "assisted-image-service" "assisted-installer-ui" "postgres"; do
      podman logs ${service} >${LOGS_DEST}/logs_${service}_${DEPLOY_TARGET}.log || true
    done
  else
    CRS=node,pod,svc,deployment,pv,pvc
    if [ ${ENABLE_KUBE_API} == "true" ]; then
      collect_kube_api_resources $KUBE_CRS
      CRS+=$(printf ",%s" "${KUBE_CRS[@]}")
    fi
    ${KUBECTL} cluster-info
    ${KUBECTL} get ${CRS} -n ${NAMESPACE} -o wide || true
    ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} logs {} -n ${NAMESPACE} --all-containers > ${LOGS_DEST}/logs_{}_${DEPLOY_TARGET}.log" || true
    ${KUBECTL} get events -n ${NAMESPACE} --sort-by=.metadata.creationTimestamp >${LOGS_DEST}/k8s_events.log || true
    ${KUBECTL} get events -n ${NAMESPACE} --sort-by=.metadata.creationTimestamp --output json >${LOGS_DEST}/k8s_events.json || true
    skipper run ./src/junit_log_parser.py --src "${LOGS_DEST}" --dst "${JUNIT_REPORT_DIR}"
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

  skipper run -e JUNIT_REPORT_DIR python3 -m src.assisted_test_infra.download_logs ${SERVICE_URL} ${LOGS_DEST} --cluster-id ${CLUSTER_ID} ${ADDITIONAL_PARAMS}
}


function download_capi_logs() {
  collect_kube_api_resources $CAPI_PROVIDER_CRS
  NAMESPACE=$(get_pod_namespace cluster-api-provider-agent)
  ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} logs {} -n ${NAMESPACE} --all-containers > ${LOGS_DEST}/logs_{}_${DEPLOY_TARGET}.log" || true
  skipper run ./src/junit_log_parser.py --src "${LOGS_DEST}" --dst "${JUNIT_REPORT_DIR}"
}

function get_pod_namespace() {
  ${KUBECTL} get pods --no-headers -A -o jsonpath='{range .items[*]}{@.metadata.name}{" "}{@.metadata.namespace}{"\n"}' | grep $1 | awk -F " " '{print $2}'
}

# This function will get the content of all given CRs from all namespaces
function collect_kube_api_resources() {
  CR_ARRAY=$1
  for CR in "${CR_ARRAY[@]}"; do
    for namespaced_name in $(${KUBECTL} get ${CR} --all-namespaces -o jsonpath='{range .items[*]}{@.metadata.namespace}{" "}{@.metadata.name}{"\n"}{end}' --no-headers); do
      ${KUBECTL} get -o json ${CR} -n ${namespaced_name} >${LOGS_DEST}/${CR}_"${namespaced_name}".json || true
    done
  done
}

"$@"
