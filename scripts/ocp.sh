#!/usr/bin/env bash
set -euo pipefail

function deploy_service() {
    kubeconfig=$1
    service_onprem=$2
    service_name=$3
    service_base_url=$4
    namespace=$5
    nodeport=""
	{
        SERVICE_BASE_URL=$service_base_url discovery-infra/update_assisted_service_cm.py
        cp $kubeconfig assisted-service/build/kubeconfig
        make config_etc_hosts_for_ocp_cluster
        make -C assisted-service/ deploy-service-on-ocp-cluster OCP_KUBECONFIG=$kubeconfig SERVICE=$service_onprem
        nodeport=$(kubectl --kubeconfig=$kubeconfig get svc/$service_name -n $namespace -o=jsonpath='{.spec.ports[0].nodePort}')
    } &>/dev/null

    read -ra def <<< "$(tail -1 /etc/hosts)"
    read -r cluster_vip <<< "$def"

    echo $cluster_vip $nodeport
}

function deploy_ui() {
    kubeconfig=$1
    service_name=$2
    namespace=$3
    nodeport=""
	{
        make config_etc_hosts_for_ocp_cluster
        make -C assisted-service/ deploy-ui-on-ocp-cluster OCP_KUBECONFIG=$kubeconfig
        nodeport=$(kubectl --kubeconfig=$kubeconfig get svc/$service_name -n $namespace -o=jsonpath='{.spec.ports[0].nodePort}')
    } &> /dev/null

    read -ra def <<< "$(tail -1 /etc/hosts)"
    read -r cluster_vip <<< "$def"

    echo $cluster_vip $nodeport
}

"$@"