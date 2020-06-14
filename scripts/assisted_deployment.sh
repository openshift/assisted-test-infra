#!/usr/bin/env bash

function destroy_all() {
    make destroy
}

function set_dns() {
  API_VIP=$(ip route show dev ${NETWORK_BRIDGE:-"tt0"} | cut -d\  -f7)
  FILE="/etc/NetworkManager/conf.d/dnsmasq.conf"
  if ! [ -f "$FILE" ]; then
    echo -e "[main]\ndns=dnsmasq" | sudo tee $FILE
  fi
  sudo truncate -s0 /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf
  echo "server=/api.${CLUSTER_NAME}.${BASE_DOMAIN}/${API_VIP}" | sudo tee -a /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf
  sudo systemctl reload NetworkManager
}

# Delete after pushing fix to dev-scripts
function wait_for_cluster() {
  echo "Nothing to do"
}


#TODO ADD ALL RELEVANT OS ENVS
function run() {
  make $1 NUM_MASTERS=$NUM_MASTERS NUM_WORKERS=$NUM_WORKERS KUBECONFIG=$PWD/minikube_kubeconfig BASE_DOMAIN=$BASE_DOMAIN CLUSTER_NAME=$CLUSTER_NAME
  retVal=$?
  echo retVal
  if [ $retVal -ne 0 ]; then
    exit $retVal
  fi
}


function run_skipper_make_command() {
    make $1
    retVal=$?
    echo retVal
    if [ $retVal -ne 0 ]; then
      exit $retVal
    fi
}


function run_without_os_envs() {
  run_skipper_make_command $1
}

"$@"