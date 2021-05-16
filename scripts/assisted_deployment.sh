#!/usr/bin/env bash

set -o nounset
set -o errexit
set -o pipefail
set -o xtrace

function set_dns() {
    NAMESPACE_INDEX=${1:-0}
    if [ "${BASE_DNS_DOMAINS:-}" != '""' ]; then
        echo "DNS registration should be handled by assisted-service"
        exit 0
    fi
    NAMESERVER_IP=$(ip route show dev tt$NAMESPACE_INDEX | cut -d\  -f7)
    if [ -z "${NAMESERVER_IP:-}" ] ; then
      NAMESERVER_IP=$(ip -o -6 address show dev tt$NAMESPACE_INDEX | awk '!/ fe80/ {e=index($4,"/"); print substr($4, 0, e-1);}')
    fi
    if [ -z "${NAMESERVER_IP:-}" ] ; then
      echo IP for interface tt$NAMESPACE_INDEX was not found
      exit 1
    fi

    update_vips

    FILE="/etc/NetworkManager/conf.d/dnsmasq.conf"
    if ! [ -f "${FILE}" ]; then
        echo -e "[main]\ndns=dnsmasq" | sudo tee $FILE
    fi
    sudo truncate -s0 /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf
    echo "server=/api.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}/${NAMESERVER_IP}" | sudo tee -a /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf
    echo "server=/.apps.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}/${NAMESERVER_IP}" | sudo tee -a /etc/NetworkManager/dnsmasq.d/openshift-${CLUSTER_NAME}.conf

    sudo systemctl reload NetworkManager

    echo "Finished setting dns"
}

function update_vips() {
    sudo virsh net-dhcp-leases test-infra-net-${NAMESPACE}
    API_VIP=$(sudo virsh net-dhcp-leases test-infra-net-${NAMESPACE} | grep api | awk '{print $5}' | cut -d"/" -f1)
    INGRESS_VIP=$(sudo virsh net-dhcp-leases test-infra-net-${NAMESPACE} | grep ingress | awk '{print $5}' | cut -d"/" -f1)

    virsh net-update test-infra-net-${NAMESPACE} delete dns-host "<host ip='192.168.126.100'><hostname>api.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}</hostname></host>"
    virsh net-update test-infra-net-${NAMESPACE} add dns-host "<host ip='${API_VIP}'><hostname>api.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}</hostname></host>"
    virsh net-update test-infra-net-${NAMESPACE} add dns-host "<host ip='${INGRESS_VIP}'><hostname>assisted-service-assisted-installer.apps.${CLUSTER_NAME}-${NAMESPACE}.${BASE_DOMAIN}</hostname></host>"
}

"$@"
