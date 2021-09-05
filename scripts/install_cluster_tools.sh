#!/bin/bash
export SUDO=$(if [ -x "$(command -v sudo)" ]; then echo "sudo"; else echo ""; fi)

function install_k3d() {
    version="v4.4.7"
    path=$(command -v k3d)

    if ! [ -x "${path}" ]; then
        echo "Installing k3d"
        wget -q -O - https://raw.githubusercontent.com/rancher/k3d/main/install.sh | TAG=${version} bash
    elif [ "$(k3d version | grep 'k3d version' | awk '{print $3}')" != "${version}" ]; then
        echo "Upgrading k3d"
        wget -q -O - https://raw.githubusercontent.com/rancher/k3d/main/install.sh | TAG=${version} bash
    else
        echo "k3d is already installed and up-to-date"
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
            curl --retry 3 -SL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.8.0-rc.0/openshift-client-linux-4.8.0-rc.0.tar.gz | tar -xz -C /usr/local/bin && break
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
install_k3d
install_kubectl
install_oc
