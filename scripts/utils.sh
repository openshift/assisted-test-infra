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

function search_for_next_free_port() {
    service=$1
    namespace=$2
    port=$3
    ip=$(get_main_ip)
    until [[ $(is_free_port $port $ip) == "free" ]]; do
          port=$(( $port + 1 ))
    done
    echo $port
}

function is_free_port() {
    port=$1
    ip=$2
    status=1
    url_reachable http://$ip:$port && status=$? || status=$?
    if [[ $status -eq 0 ]]; then
          return
    fi
    delete_xinetd_files_by_substr :$port
    echo "free"
}


function delete_xinetd_files_by_substr() {
    substr=$1
    sudo systemctl stop xinetd
    for name in $(sudo ls /etc/xinetd.d/ | grep $substr); do
        sudo rm /etc/xinetd.d/$name -f
    done
    sudo systemctl start xinetd
}

function spawn_port_forwarding_command() {
    service_name=$1
    external_port=$2
    namespace=$3

    filename=$service_name:$namespace:$external_port

    cat <<EOF >build/xinetd-$filename
service ${service_name}
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
    sudo mv build/xinetd-$filename /etc/xinetd.d/$filename --force
    sudo systemctl restart xinetd
}

function run_in_background() {
    bash -c "nohup $1  >/dev/null 2>&1 &"
}

function kill_all_port_forwardings() {
    services=$1
    sudo systemctl stop xinetd
    for s in $services; do
        for f in $(sudo ls /etc/xinetd.d/ | grep $s); do
            sudo rm -f /etc/xinetd.d/$f
        done
    done
}

function get_main_ip() {
    echo "$(ip route get 1 | sed 's/^.*src \([^ ]*\).*$/\1/;q')"
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
