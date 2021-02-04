#!/bin/sh
set -euo pipefail

echo "Opening port in firewall"
firewall-cmd --add-port=443/tcp --zone=libvirt

echo "Copying configuration files"
sudo cp scripts/haproxy.cfg scripts/choose_backend.lua /etc/haproxy/

echo "Restarting haproxy service"
sudo systemctl restart haproxy
