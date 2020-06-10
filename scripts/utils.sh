#!/usr/bin/env bash

set -o nounset

export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}


function print_log() {
  echo "$(basename $0): $1"
}

function url_reachable() {
    curl -s $1 --max-time 4 > /dev/null
    return $?
}

function spawn_port_forwarding_command() {
  service_name=$1
  external_port=$2

  cat << EOF > /etc/xinetd.d/${service_name}
service ${service_name}
{
  flags		= IPv4
  bind		= 0.0.0.0
  type		= UNLISTED
  socket_type	= stream
  protocol	= tcp
  user		= root
  wait		= no
  redirect	= $(minikube ip) $(kubectl --kubeconfig=${KUBECONFIG} get svc/${service_name} -n assisted-installer -o=jsonpath='{.spec.ports[0].nodePort}')
  port		= ${external_port}
  only_from	= 0.0.0.0/0
  per_source	= UNLIMITED
}
EOF

  systemctl start xinetd
  systemctl reload xinetd
}

function run_in_background() {
  bash -c "nohup $1  >/dev/null 2>&1 &"
}

function kill_all_port_forwardings() {
  systemctl stop xinetd
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

      RETRIES=$((RETRIES-1))

      echo "Running given function"
      $2

      echo "Sleeping for 30 seconds"
      sleep 30s

      echo "Verifying url and port are accesible"
      url_reachable "$1" && STATUS=$? || STATUS=$?
    done
    if [ $RETRIES -eq 0 ]; then
      echo "Timeout reached, url $1 not reachable"
      exit 1
    fi
}

"$@"
