#!/usr/bin/env bash

set -o nounset
set -o errexit
set -o pipefail

KIND_VERSION="0.17.0"

__dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

function check() {
	if [ "$(kind --version)" == "kind version $KIND_VERSION" ]; then
		return 0
	else
		echo "Does not have 'kind' with version $KIND_VERSION!"
		return 1
	fi
}

function install() {
	if check; then
		return 0
	fi

	echo "Installing kind $KIND_VERSION..."
	sudo curl --retry 5 --connect-timeout 30 -L https://kind.sigs.k8s.io/dl/v$KIND_VERSION/kind-linux-amd64 -o /usr/local/bin/kind
	sudo chmod u+x /usr/local/bin/kind
	echo "Installed successfully!"
}

function setup_contour() {
	# based on https://kind.sigs.k8s.io/docs/user/ingress/#contour
	# for more information about contour, see: https://projectcontour.io
	kubectl apply -f https://projectcontour.io/quickstart/contour.yaml
	kubectl rollout status -n projectcontour daemonset envoy --timeout 2m
	kubectl rollout status -n projectcontour deployment contour --timeout 2m
}

function create() {
	check

	if ! kind export kubeconfig &> /dev/null ; then
		KIND_EXPERIMENTAL_PROVIDER=podman kind create cluster --config $__dir/kind-config.yaml
	else
		echo "Cluster already existing. Skipping creation"
	fi

	setup_contour
}

function delete() {
	kind delete cluster
}

if [ $# -eq 0 ]; then
	echo "Usage: $__dir/kind.sh (install|check|create)"
	exit 1
else
	$@
fi
