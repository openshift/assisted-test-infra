#!/usr/bin/env bash
set -euo pipefail
set -o xtrace

PROVIDER_REPO="${PROVIDER_REPO:-https://github.com/eranco74/cluster-api-provider-agent.git}"
PROVIDER_BRANCH="${PROVIDER_BRANCH:-master}"
PROVIDER_IMAGE="${PROVIDER_IMAGE:-quay.io/eranco74/cluster-api-provider-agent:latest}"
HYPERSHIFT_REPO="${HYPERSHIFT_REPO:-https://github.com/avishayt/hypershift}"
HYPERSHIFT_BRANCH="${HYPERSHIFT_BRANCH:-master}"
HYPERSHIFT_IMAGE="${HYPERSHIFT_IMAGE:-quay.io/eranco74/hypershift:latest}"
BASE_DIR=capi

function clone_repo()
{
  if [[ ! -d "$BASE_DIR/$2" ]]
  then
    echo "Cloning $1.";
    git clone $1 $BASE_DIR/$2;
	fi
}

function checkout_branch()
{
  	(cd capi/$1;
  	git fetch;
  	git checkout $2)
}

deploy_provider()
{
  clone_repo "$PROVIDER_REPO" provider
  checkout_branch provider "$PROVIDER_BRANCH"
  make -C capi/provider deploy IMG="$PROVIDER_IMAGE"
}

deploy_hypershift()
{
  kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.51.1/bundle.yaml || true
  clone_repo $HYPERSHIFT_REPO hypershift
  checkout_branch hypershift "$HYPERSHIFT_BRANCH"
  make -C capi/hypershift build
  capi/hypershift/bin/hypershift install --hypershift-image "$HYPERSHIFT_IMAGE"
}

source scripts/install_golang.sh
mkdir -p $BASE_DIR
deploy_provider
deploy_hypershift
echo "Alow route to minikube network - required for hosts to pull ignition"
iptables -D LIBVIRT_FWI -o virbr1 -j REJECT --reject-with icmp-port-unreachable || true
