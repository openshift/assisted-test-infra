#!/usr/bin/env bash

set -o errexit

function error () {
    echo $@ 1>&2
}

echo "Installing environment"
scripts/install_environment.sh
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
