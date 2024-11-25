#!/usr/bin/env bash

set -o nounset
set -o errexit
set -o pipefail
set -o xtrace

source scripts/utils.sh

NAMESPACE=${NAMESPACE:-assisted-installer}
CLUSTER_ID=${CLUSTER_ID:-""}
ADDITIONAL_PARAMS=${ADDITIONAL_PARAMS:-""}
KUBECTL=${KUBECTL:-kubectl}
LOGS_DEST=${LOGS_DEST:-build}
JUNIT_REPORT_DIR=${JUNIT_REPORT_DIR:-"reports/"}
KUBE_CRS=(clusterdeployment infraenv agentclusterinstall agent)
CAPI_PROVIDER_CRS=(agentmachine agentcluster cluster machine machinedeployment machineset nodepool)
HYPERSHIFT_CRS=(hostedcluster hostedcontrolplane)
ENABLE_KUBE_API=${ENABLE_KUBE_API:-"false"}
DEBUG_FLAGS=${DEBUG_FLAGS:-""}
export LOGGER_NAME="download_logs"

function download_service_logs() {
  mkdir -p ${LOGS_DEST} || true

  if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
    podman ps -a || true

    for service in "assisted-installer-db" "assisted-installer-image-service" "assisted-installer-service" "assisted-installer-ui"; do
      podman logs ${service} >${LOGS_DEST}/logs_${service}_${DEPLOY_TARGET}.log 2>&1 || true
    done
  else
    CRS=node,pod,svc,deployment,pv,pvc
    if [ ${ENABLE_KUBE_API} == "true" ]; then
      collect_kube_api_resources "${KUBE_CRS[@]}"
      CRS+=$(printf ",%s" "${KUBE_CRS[@]}")
    fi
    ${KUBECTL} cluster-info
    ${KUBECTL} get ${CRS} -n ${NAMESPACE} -o wide || true
    ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} logs {} -n ${NAMESPACE} --all-containers > ${LOGS_DEST}/logs_{}_${DEPLOY_TARGET}.log" || true
    ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} get pods {} -n ${NAMESPACE} -o yaml > ${LOGS_DEST}/pods_{}_${DEPLOY_TARGET}.yaml" || true
    ${KUBECTL} get events -n ${NAMESPACE} --sort-by=.metadata.creationTimestamp >${LOGS_DEST}/k8s_events.log || true
    ${KUBECTL} get nodes -o yaml >${LOGS_DEST}/k8s_nodes.yaml || true
    ${KUBECTL} get events -n ${NAMESPACE} --sort-by=.metadata.creationTimestamp --output json >${LOGS_DEST}/k8s_events.json || true
    skipper run ./src/junit_log_parser.py --src "${LOGS_DEST}" --dst "${JUNIT_REPORT_DIR}"
  fi
}

function download_cluster_logs() {

  if [ ${ENABLE_KUBE_API} == "true" ]; then
      skipper run -e JUNIT_REPORT_DIR python3 -m src.assisted_test_infra.download_logs "no_url" ${LOGS_DEST} ${ADDITIONAL_PARAMS}
  else
    if [ "${REMOTE_SERVICE_URL:-}" != '""' ]; then
      SERVICE_URL=${REMOTE_SERVICE_URL}
    else
      if [ "${DEPLOY_TARGET:-}" = "onprem" ]; then
        SERVICE_URL=http://localhost:8090
      elif [ "${DEPLOY_TARGET:-}" = "minikube" ]; then
        SERVICE_URL=$(KUBECONFIG=${HOME}/.kube/config minikube service assisted-service -n ${NAMESPACE} --url)
      else
        SERVICE_URL="${SERVICE_URL:-$(get_main_ip)}:8090"
      fi
    fi
    skipper run -e JUNIT_REPORT_DIR "python3 ${DEBUG_FLAGS} -m src.assisted_test_infra.download_logs ${SERVICE_URL} ${LOGS_DEST} --cluster-id ${CLUSTER_ID} ${ADDITIONAL_PARAMS}"
  fi
}


function download_capi_logs() {
  collect_kube_api_resources "${CAPI_PROVIDER_CRS[@]}"
  # get hypershfit CRs and logs
  collect_kube_api_resources "${HYPERSHIFT_CRS[@]}"
  mkdir -p ${LOGS_DEST}/hypershift
  ${KUBECTL} logs deployment/operator -n hypershift > ${LOGS_DEST}/hypershift/logs_operator.log
  ${KUBECTL} get events -n hypershift > ${LOGS_DEST}/hypershift/logs_events.log
  # The pod name is capi-provider in case it's deployed by hypershift
  NAMESPACE=$(get_pod_namespace "capi-provider|cluster-api-provider-agent")
  mkdir ${LOGS_DEST}/${NAMESPACE}
  ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} logs {} -n ${NAMESPACE} --all-containers > ${LOGS_DEST}/${NAMESPACE}/logs_{}.log" || true
  ${KUBECTL} get pods -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} get pods -o yaml {} -n ${NAMESPACE} > ${LOGS_DEST}/${NAMESPACE}/pods_{}}.yaml" || true
  ${KUBECTL} get cm -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} get cm -o yaml {} -n ${NAMESPACE} > ${LOGS_DEST}/${NAMESPACE}/cm_{}.yaml" || true
  ${KUBECTL} get cm -n ${NAMESPACE} -o=custom-columns=NAME:.metadata.name --no-headers | xargs -r -I {} sh -c "${KUBECTL} get secret -o yaml {} -n ${NAMESPACE} > ${LOGS_DEST}/${NAMESPACE}/secret_{}.yaml" || true
  ${KUBECTL} get events -n ${NAMESPACE} > ${LOGS_DEST}/${NAMESPACE}/events.yaml || true
  skipper run ./src/junit_log_parser.py --src "${LOGS_DEST}" --dst "${JUNIT_REPORT_DIR}"
}

function get_pod_namespace() {
  ${KUBECTL} get pods --no-headers -A -o jsonpath='{range .items[*]}{@.metadata.name}{" "}{@.metadata.namespace}{"\n"}' | egrep $1 | awk -F " " '{print $2}'
}

# This function will get the content of all given CRs from all namespaces
function collect_kube_api_resources() {
  CR_ARRAY=("$@")
  for CR in "${CR_ARRAY[@]}"; do
    for namespace in $(${KUBECTL} get ${CR} --all-namespaces -o jsonpath='{.items..metadata.namespace}' --no-headers); do
      for name in $(${KUBECTL} get ${CR} -n ${namespace} -o jsonpath='{.items..metadata.name}' --no-headers); do
        ${KUBECTL} get -o json ${CR} -n ${namespace} ${name} > ${LOGS_DEST}/${CR}_${namespace}_${name}.json || true
      done
    done
  done
}

"$@"
