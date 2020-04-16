#!/usr/bin/env bash

echo "Installing environment"
scripts/install_environment.sh
echo "Done installing"

echo "Creating image"
make image_build
echo "Done creating image"

echo "Install and start minikube"
make start_minikube