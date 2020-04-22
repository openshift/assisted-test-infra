#!/usr/bin/env bash

echo "Installing environment"
sudo scripts/install_environment.sh
echo "Done installing"

echo "Creating image"
make image_build
echo "Done creating image"

if [ -z "${NO_MINIKUBE}" ]; then
  echo "Install and start minikube"
  make start_minikube
fi
