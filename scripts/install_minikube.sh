#!/bin/bash
set -euxo pipefail
export SUDO=$(if [ -x "$(command -v sudo)" ]; then echo "sudo"; else echo ""; fi)


function install_minikube() {
    minikube_version=v1.25.2
    curl --retry 3 -Lo minikube https://storage.googleapis.com/minikube/releases/${minikube_version}/minikube-linux-amd64
    ${SUDO} install minikube /usr/local/bin/
    minikube version
    rm -f minikube
}

function install_kubectl() {
    kubectl_version=v1.23.0
    curl --retry 3 -LO https://dl.k8s.io/release/${kubectl_version}/bin/linux/amd64/kubectl
    chmod +x kubectl

    curl -LO https://dl.k8s.io/${kubectl_version}/bin/linux/amd64/kubectl.sha256
    echo "$(<kubectl.sha256)  kubectl" | sha256sum --check
    ${SUDO} install kubectl /usr/local/bin/
    rm -f kubectl.sha256 kubectl
    kubectl
}

function install_oc() {
    if ! [ -x "$(command -v oc)" ]; then
        echo "Installing oc..."
        for i in {1..4}; do
            curl --retry 3 -SL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable-4.8/openshift-client-linux.tar.gz | tar -xz -C /usr/local/bin && break
            echo "oc installation failed. Retrying again in 5 seconds..."
            sleep 5
        done
    else
        echo "oc is already installed"
    fi
}


install_minikube
install_kubectl
install_oc
