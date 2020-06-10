#!/usr/bin/env bash

set -o errexit
set -o nounset

function error () {
    echo $@ 1>&2
}

# Check OS
OS=$(awk -F= '/^ID=/ { print $2 }' /etc/os-release | tr -d '"')
if [[ ! ${OS} =~ ^(centos)$ ]]; then
  error "\"${OS}\" is an unsupported OS. We support only CentOS."
  exit 1
fi

#Check CentOS version
VER=$(awk -F= '/^VERSION_ID=/ { print $2 }' /etc/os-release | tr -d '"' | cut -f1 -d'.')
VER_SUPPORTED=8

if [[ ${VER} -ne ${VER_SUPPORTED} ]]; then
  error "CentOS version ${VER_SUPPORTED} is required."
  exit 1
fi

echo "Installing environment"
sudo scripts/install_environment.sh
echo "Done installing"

echo "Creating image"
make image_build
echo "Done creating image"

echo "Installing minikube and oc"
make install_minikube

if [ -z "${NO_MINIKUBE}" ]; then
  echo "Install and start minikube"
  make start_minikube
fi
