#!/usr/bin/env bash

source scripts/utils.sh

function destroy_all() {
    make destroy
}

function set_dns() {
    NAMESPACE_INDEX=${1:-0}
    if [ "${BASE_DNS_DOMAINS}" != '""' ]; then
        echo "DNS registration should be handled by assisted-service"
        exit 0
    fi
    NAMESERVER_IP=$(ip route show dev tt$NAMESPACE_INDEX | cut -d\  -f7)
    if [ -z "${NAMESERVER_IP}" ] ; then
      NAMESERVER_IP=$(ip -o -6 address show dev tt$NAMESPACE_INDEX | awk '!/ fe80/ {e=index($4,"/"); print substr($4, 0, e-1);}')
    fi
    if [ -z "${NAMESERVER_IP}" ] ; then
      echo IP for interface tt$NAMESPACE_INDEX was not found
      exit 1
    fi

    FILE="/etc/NetworkManager/conf.d/dnsmasq.conf"
    if ! [ -f "${FILE}" ]; then
        echo -e "[main]\ndns=dnsmasq" | sudo tee $FILE
    fi

    sudo truncate -s0 /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf
    echo "server=/api.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}/${NAMESERVER_IP}" | sudo tee -a /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf
    echo "server=/.apps.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}/${NAMESERVER_IP}" | sudo tee -a /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf

    sudo systemctl reload NetworkManager

    HOST_IP=$(get_main_ip)
    if ! grep -q "${HOST_IP}" /etc/resolv.conf; then
        sed -i "0,/nameserver/s/nameserver/nameserver ${HOST_IP}\nnameserver/" /etc/resolv.conf
    fi

    echo "Finished setting dns"
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
