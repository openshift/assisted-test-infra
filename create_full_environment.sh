#!/usr/bin/env bash

set -o errexit

function error() {
    echo $@ 1>&2
}

# Check OS
OS=$(awk -F= '/^ID=/ { print $2 }' /etc/os-release | tr -d '"')
if [[ ! ${OS} =~ ^(centos)$ ]] && [[ ! ${OS} =~ ^(rhel)$ ]] && [[ ! ${OS} =~ ^(fedora)$ ]]; then
    error "\"${OS}\" is an unsupported OS. We support only CentOS, RHEL or FEDORA."
    exit 1
fi

#Check CentOS version
VER=$(awk -F= '/^VERSION_ID=/ { print $2 }' /etc/os-release | tr -d '"' | cut -f1 -d'.')
VER_SUPPORTED=8

if [[ ${OS} =~ ^(centos)$ && ${VER} -ne ${VER_SUPPORTED} ]]; then
    error "CentOS version ${VER_SUPPORTED} is required."
    exit 1
elif [[ ${OS} =~ ^(rhel)$ && ${VER} -ne ${VER_SUPPORTED} ]]; then
    error "RHEL version ${VER_SUPPORTED} is required."
    exit 1
fi
# TODO add minimum version fedora validation

echo "Installing environment"
scripts/install_environment.sh
echo "Done installing"

echo "Creating image"
make image_build
echo "Done creating image"

echo "Installing minikube and oc"
scripts/install_minikube.sh
echo "Done installing minikube and oc"

if [ -z "${NO_MINIKUBE}" ]; then
    echo "Install and start minikube"
    make start_minikube
fi
