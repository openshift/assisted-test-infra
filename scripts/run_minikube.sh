#!/bin/bash

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
    for p in $(virsh -c qemu:///system list --name ); do
        if [[ $p == $PROFILE ]]; then
            return
        fi
    done

    minikube start --driver=kvm2 --memory=8192 --profile=$PROFILE --force
}

configure_minikube
init_minikube
