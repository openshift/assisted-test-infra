#!/bin/bash
set -euxo pipefail
export SUDO=$(if [ -x "$(command -v sudo)" ]; then echo "sudo"; else echo ""; fi)

function install_kubectl() {
    kubectl_version=v1.23.0
    curl --retry 3 --connect-timeout 30 -LO https://dl.k8s.io/release/${kubectl_version}/bin/linux/amd64/kubectl
    chmod +x kubectl

    curl --retry 3 --connect-timeout 30 -LO https://dl.k8s.io/${kubectl_version}/bin/linux/amd64/kubectl.sha256
    echo "$(<kubectl.sha256)  kubectl" | sha256sum --check
    ${SUDO} install kubectl /usr/local/bin/
    rm -f kubectl.sha256 kubectl

    which kubectl > /dev/null
}

function install_oc() {
    if [ -x "$(command -v oc)" ]; then
        echo "oc is already installed"
        return
    fi

    echo "Installing oc..."
    for i in {1..4}; do
        curl --retry 3 --connect-timeout 30 -SL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable-4.12/openshift-client-linux.tar.gz | sudo tar -xz -C /usr/local/bin && break
        echo "oc installation failed. Retrying again in 5 seconds..."
        sleep 5
    done

    which oc > /dev/null
}

install_kubectl
install_oc
