#!/bin/bash
export SUDO=$(if [ -x "$(command -v sudo)" ]; then echo "sudo"; else echo ""; fi)

function install_minikube() {
    if [ "${DEPLOY_TARGET}" != "minikube" ]; then
        echo "Skips installing minikube when deployment target is ${DEPLOY_TARGET}..."
        return
    fi

    minikube_version=v1.18.1
    minikube_path=$(command -v minikube)
    if ! [ -x "$minikube_path" ] || [ $(minikube version -o json | jq -r '.minikubeVersion') != $minikube_version ]; then
        echo "Installing minikube..."
        arkade get minikube --version=$minikube_version
        ${SUDO} mv ${HOME}/.arkade/bin/minikube /usr/local/bin/
    else
        echo "minikube is already installed"
    fi
}

function install_kubectl() {
    if ! [ -x "$(command -v kubectl)" ]; then
        echo "Installing kubectl..."
        arkade get kubectl --version=v1.20.0
        ${SUDO} mv ${HOME}/.arkade/bin/kubectl /usr/local/bin/
    else
        echo "kubectl is already installed"
    fi
}

function install_oc() {
    if ! [ -x "$(command -v oc)" ]; then
        echo "Installing oc..."
        for i in {1..4}; do
            curl --retry 3 -SL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.6.0/openshift-client-linux-4.6.0.tar.gz | tar -xz -C /usr/local/bin && break
            echo "command failed. Retrying again in 5 seconds..."
            sleep 5
        done
    else
        echo "oc is already installed"
    fi
}

function install_arkade() {
    if ! [ -x "$(command -v arkade)" ]; then
        echo "Installing arkade..."
        curl -sLS https://dl.get-arkade.dev | ${SUDO} sh
    else
        echo "arkade is already installed"
    fi
}

install_arkade
install_minikube
install_kubectl
install_oc
