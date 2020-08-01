#!/bin/bash

export NAMESPACE=${NAMESPACE:-assisted-installer}
export PROFILE=${PROFILE:-assisted-installer}

function configure_minikube() {
    echo "Configuring minikube..."
    minikube config set ShowBootstrapperDeprecationNotification false
    minikube config set WantUpdateNotification false
    minikube config set WantReportErrorPrompt false
    minikube config set WantKubectlDownloadMsg false
}

function init_minikube() {
    #If the vm exists, it has already been initialized
    if [[ -z "$(virsh -c qemu:///system list --name | grep $PROFILE)" ]]; then
        minikube start --driver=kvm2 --profile $PROFILE --memory=8192 --force
    fi
}

configure_minikube
init_minikube
