#!/bin/bash
export SUDO=$(if [ -x "$(command -v sudo)" ]; then echo "sudo"; else echo ""; fi)

function install_minikube() {
    if [ "${DEPLOY_TARGET}" != "minikube" ]; then
        echo "Skips installing minikube when deployment target is ${DEPLOY_TARGET}..."
        return
    fi

    if ! [ -x "$(command -v minikube)" ]; then
        echo "Installing minikube..."
        curl --retry 3 -Lo minikube https://storage.googleapis.com/minikube/releases/v1.8.2/minikube-linux-amd64
        chmod +x minikube
        ${SUDO} cp minikube /usr/local/sbin/
    else
        echo "minikube is already installed"
    fi
}

function install_kubectl() {
    if ! [ -x "$(command -v kubectl)" ]; then
        echo "Installing kubectl..."
        curl --retry 3 -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/v1.17.0/bin/linux/amd64/kubectl
        chmod +x kubectl
        ${SUDO} mv kubectl /usr/local/sbin/
    else
        echo "kubectl is already installed"
    fi
}

function install_oc() {
    if ! [ -x "$(command -v oc)" ]; then
        echo "Installing oc..."
        for i in {1..4}; do
            curl --retry 3 -SL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.6.0/openshift-client-linux-4.6.0.tar.gz | tar -xz -C /usr/local/sbin && break
            echo "command failed. Retrying again in 5 seconds..."
            sleep 5
        done
    else
        echo "oc is already installed"
    fi
}

install_minikube
install_kubectl
install_oc
