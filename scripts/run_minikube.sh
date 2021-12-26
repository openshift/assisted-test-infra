#!/bin/bash

source scripts/utils.sh

set -o nounset
set -o pipefail
set -o errexit
set -o xtrace

MINIKUBE_DISK_SIZE="${MINIKUBE_DISK_SIZE:-50g}"
MINIKUBE_RAM_MB="${MINIKUBE_RAM_MB:-8192}"

function configure_minikube() {
    echo "Configuring minikube..."
    minikube config set WantUpdateNotification false
}

function init_minikube() {
    #If the vm exists, it has already been initialized
    for p in $(virsh -c qemu:///system list --name ); do
        if [[ $p == minikube ]]; then
            return
        fi
    done

    for i in {1..5}
    do
        minikube delete
        minikube start --driver=kvm2 --memory="${MINIKUBE_RAM_MB}" --cpus=4 --force --wait-timeout=15m0s --disk-size="${MINIKUBE_DISK_SIZE}" --addons=registry || true

        if minikube status ; then
            break
        else
          minikube logs
        fi
    done

    minikube status
    minikube tunnel --cleanup &> /dev/null &
}

if [ "${DEPLOY_TARGET}" != "minikube" ]; then
    exit 0
fi

configure_minikube
as_singleton init_minikube
