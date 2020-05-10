#!/usr/bin/env bash

source scripts/utils.sh

function create_port_forwarding() {
  kubectl --kubeconfig=${KUBECONFIG} port-forward deployment/$3 $1:$2 --address 0.0.0.0
}

while kubectl --kubeconfig=${KUBECONFIG} get deployment | grep $3; do
  create_port_forwarding $1 $2 $3
done
