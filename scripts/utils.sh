#!/usr/bin/env bash

set -o nounset

export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
export NAMESPACE=${NAMESPACE:-assisted-installer}

function print_log() {
    echo "$(basename $0): $1"
}

function url_reachable() {
    curl -s $1 --max-time 4 >/dev/null
    return $?
}

function spawn_port_forwarding_command() {
    service_name=$1
    external_port=$2

    cat <<EOF >build/xinetd-$service_name-$NAMESPACE
service $service_name-$NAMESPACE
{
  flags		= IPv4
  bind		= 0.0.0.0
  type		= UNLISTED
  socket_type	= stream
  protocol	= tcp
  user		= root
  wait		= no
  redirect	= $(minikube ip) $(kubectl --kubeconfig=${KUBECONFIG} get svc/${service_name} -n ${NAMESPACE} -o=jsonpath='{.spec.ports[0].nodePort}')
  port		= ${external_port}
  only_from	= 0.0.0.0/0
  per_source	= UNLIMITED
}
EOF
    sudo mv build/xinetd-$service_name-$NAMESPACE /etc/xinetd.d/$service_name-$NAMESPACE --force
    sudo systemctl restart xinetd
}

function run_in_background() {
    bash -c "nohup $1  >/dev/null 2>&1 &"
}

function kill_all_port_forwardings() {
    sudo systemctl stop xinetd
}

function get_main_ip() {
    echo "$(ip route get 1 | sed 's/^.*src \([^ ]*\).*$/\1/;q')"
}


function get_service_port() {
    service=$1
    ns=$2
    deallocate_existing_service_port $service $ns

    host=$3
    start_port=$4
    echo $(first_unreachable_port $host $start_port)
}

function deallocate_existing_service_port() {
    service=$1
    ns=$2
    if sudo test -f /etc/xinetd.d/$service-$ns; then
        sudo systemctl stop xinetd
        sudo rm /etc/xinetd.d/$service-$ns --force
        sudo systemctl start xinetd
    fi
}

function first_unreachable_port() {
    host=$1
    port=$2
    reachable=1
    url_reachable "http://$host:$port" && reachable=$? || reachable=$?

    while [ $reachable -eq 0 ]; do
        port=$(( $port + 1 ))
        url_reachable "http://$host:$port" && reachable=$? || reachable=$?
    done

    echo $port
}

function wait_for_url_and_run() {
    RETRIES=15
    RETRIES=$((RETRIES))
    STATUS=1
    url_reachable "$1" && STATUS=$? || STATUS=$?

    until [ $RETRIES -eq 0 ] || [ $STATUS -eq 0 ]; do

        RETRIES=$((RETRIES - 1))

        echo "Running given function"
        $2

        echo "Sleeping for 30 seconds"
        sleep 30s

        echo "Verifying URL and port are accessible"
        url_reachable "$1" && STATUS=$? || STATUS=$?
    done
    if [ $RETRIES -eq 0 ]; then
        echo "Timeout reached, URL $1 not reachable"
        exit 1
    fi
}

function close_external_ports() {
    sudo firewall-cmd --zone=public --remove-port=6000/tcp
    sudo firewall-cmd --zone=public --remove-port=6008/tcp
}

"$@"
