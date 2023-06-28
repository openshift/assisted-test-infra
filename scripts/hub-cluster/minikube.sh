#!/usr/bin/env bash

source scripts/utils.sh

set -o nounset
set -o pipefail
set -o errexit
set -o xtrace

MINIKUBE_DISK_SIZE="${MINIKUBE_DISK_SIZE:-50g}"
MINIKUBE_RAM_MB="${MINIKUBE_RAM_MB:-8192}"
export SUDO=$(if [ -x "$(command -v sudo)" ]; then echo "sudo"; else echo ""; fi)

__dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

function _configure_minikube() {
    echo "Configuring minikube..."
    minikube config set WantUpdateNotification false
}

function _init_minikube() {
    #If the vm exists, it has already been initialized
    for p in $(virsh -c qemu:///system list --name ); do
        if [[ $p == minikube ]]; then
            return
        fi
    done

    for i in {1..5}
    do
        minikube delete
        minikube start --driver=kvm2 --memory="${MINIKUBE_RAM_MB}" --cpus=4 --force --wait-timeout=15m0s --disk-size="${MINIKUBE_DISK_SIZE}" || true

        if minikube status ; then
            break
        else
          minikube logs || true
          systemctl restart libvirtd.service || true
        fi
    done

    minikube status
    minikube addons enable registry --images="Registry=quay.io/libpod/registry:2.8"
    minikube update-context
    minikube tunnel --cleanup &> /dev/null &
}

function install() {
    minikube_version=v1.25.2
    curl --retry 3 --connect-timeout 30 -Lo minikube https://storage.googleapis.com/minikube/releases/${minikube_version}/minikube-linux-amd64
    ${SUDO} install minikube /usr/local/bin/
    minikube version
    rm -f minikube
}

function create() {
    _configure_minikube
    as_singleton _init_minikube

    # Change the registry service type to LoadBalancer to be able to access it from outside the cluster
    kubectl patch service registry -n kube-system --type json -p='[{"op": "replace", "path": "/spec/type", "value":"LoadBalancer"}]'
    # Forward the minikube registry addon k8s service to the host to push the debug image using localhost:5000
    spawn_port_forwarding_command registry 5000 kube-system 999 $KUBECONFIG minikube undeclaredip 80 registry

    eval $(minikube docker-env)
}

function delete() {
    minikube delete --all --purge
}

if [ $# -eq 0 ]; then
	echo "Usage: $__dir/minikube.sh (install|create)"
	exit 1
else
	$@
fi
