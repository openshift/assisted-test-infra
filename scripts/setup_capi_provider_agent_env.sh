#!/usr/bin/env bash
set -euo pipefail
set -o xtrace

PROVIDER_REPO="${PROVIDER_REPO:-https://github.com/openshift/cluster-api-provider-agent.git}"
PROVIDER_BRANCH="${PROVIDER_BRANCH:-master}"
PROVIDER_IMAGE="${PROVIDER_IMAGE:-quay.io/edge-infrastructure/cluster-api-provider-agent:latest}"
HYPERSHIFT_REPO="${HYPERSHIFT_REPO:-https://github.com/openshift/hypershift}"
HYPERSHIFT_BRANCH="${HYPERSHIFT_BRANCH:-main}"
HYPERSHIFT_IMAGE="${HYPERSHIFT_IMAGE:-quay.io/hypershift/hypershift:latest}"
BASE_DIR=build

function clone_repo() {
  if [[ ! -d "$BASE_DIR/$2" ]]; then
    echo "Cloning $1."
    git clone $1 $BASE_DIR/$2
  fi
}

function checkout_branch() {
  (
    cd $BASE_DIR/$1
    git fetch
    git checkout -B $2 origin/$2
  )
}

function waitForPodsReadyStatus(){
  while [[ $(kubectl get pods -n $1 -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}'| tr ' ' '\n'  | sort -u) != "True" ]]; do
    echo "Waiting for pods in namespace $1 to be ready"
    kubectl get pods -n $1 -o 'jsonpath={..status.containerStatuses}' | jq
    sleep 5;
  done
  echo "Pods in namespace $1 are ready"
}

deploy_provider() {
  clone_repo "$PROVIDER_REPO" provider
  checkout_branch provider "$PROVIDER_BRANCH"
  make -C $BASE_DIR/provider deploy IMG="$PROVIDER_IMAGE"
}

deploy_hypershift() {
  kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.51.1/bundle.yaml || true
  clone_repo $HYPERSHIFT_REPO hypershift
  checkout_branch hypershift "$HYPERSHIFT_BRANCH"
  make -C $BASE_DIR/hypershift build
  $BASE_DIR/hypershift/bin/hypershift install --hypershift-image "$HYPERSHIFT_IMAGE"
  waitForPodsReadyStatus hypershift
}

mkdir -p $BASE_DIR
deploy_provider
deploy_hypershift
echo "Alow route to minikube network - required for hosts to pull ignition"
iptables -D LIBVIRT_FWI -o virbr1 -j REJECT --reject-with icmp-port-unreachable || true
