#!/usr/bin/env bash
set -euo pipefail

function deploy_service() {
    kubeconfig=$1
    service=$2
    service_name=$3
    service_base_url=$4
    namespace=$5
    controller_image=$6
    nodeport=""

    SERVICE_BASE_URL=$service_base_url discovery-infra/update_assisted_service_cm.py
    cp $kubeconfig assisted-service/build/kubeconfig
    make config_etc_hosts_for_ocp_cluster
    make -C assisted-service/ deploy-service-on-ocp-cluster OCP_KUBECONFIG=$kubeconfig SERVICE=$service CONTROLLER_OCP=$controller_image
    nodeport=$(kubectl --kubeconfig=$kubeconfig get svc/$service_name -n $namespace -o=jsonpath='{.spec.ports[0].nodePort}')

    read -ra def <<< "$(tail -1 /etc/hosts)"
    read -r cluster_vip <<< "$def"

    echo $cluster_vip $nodeport
}

function deploy_ui() {
    kubeconfig=$1
    service_name=$2
    namespace=$3
    nodeport=""

    make config_etc_hosts_for_ocp_cluster
    make -C assisted-service/ deploy-ui-on-ocp-cluster OCP_KUBECONFIG=$kubeconfig
    nodeport=$(kubectl --kubeconfig=$kubeconfig get svc/$service_name -n $namespace -o=jsonpath='{.spec.ports[0].nodePort}')

    read -ra def <<< "$(tail -1 /etc/hosts)"
    read -r cluster_vip <<< "$def"

    echo $cluster_vip $nodeport
}

function deploy_controller() {
    kubeconfig=$1
    service_base_url=$2
    cluster_id=$3
    namespace=$4
    controller_image=$5

    mkdir -p assisted-installer/build
    cp $kubeconfig assisted-installer/build/kubeconfig
    make -C assisted-installer/ deploy_controller_on_ocp_cluster OCP_KUBECONFIG=$kubeconfig \
        SERVICE_BASE_URL=$service_base_url CLUSTER_ID=$cluster_id CONTROLLER_OCP=$controller_image
}

"$@"
