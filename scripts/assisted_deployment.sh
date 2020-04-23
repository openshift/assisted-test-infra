#!/usr/bin/env bash


#TODO ADD ALL RELEVANT OS ENVS
function run() {
    /usr/local/bin/skipper make $1 NUM_MASTERS=$NUM_MASTERS NUM_WORKERS=$NUM_WORKERS KUBECONFIG=$PWD/minikube_kubeconfig BASE_DOMAIN=$BASE_DOMAIN CLUSTER_NAME=$CLUSTER_NAME
}


function destroy_all() {
    /usr/local/bin/skipper make destroy
}
