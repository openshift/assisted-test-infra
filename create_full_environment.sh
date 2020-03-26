#!/usr/bin/env bash

echo "Installing environment"
scripts/install_environment.sh
echo "Done installing"

echo "Creating image"
make image_build
echo "Done creating image"

echo "Bring vm inventory"
skipper make bring_bm_inventory
echo "Done bringing bring_bm_inventory"

echo "Install and start minikube"
make start_minikube