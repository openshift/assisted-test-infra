#!/usr/bin/env bash

echo "Installing environment"
sudo scripts/install_environment.sh
echo "Done installing"

echo "Creating image"
make image_build
echo "Done creating image"

echo "Install and start minikube"
make start_minikube

echo "Starting cluster"
/usr/local/bin/skipper make run_full_flow
