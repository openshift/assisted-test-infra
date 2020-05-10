#!/usr/bin/env bash

export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}


function url_reachable() {
    curl -s $1 --max-time 4 > /dev/null
    return $?
}


function spawn_port_forwarding_command() {
  kill_portforwarding_loop $1 $2 $3
  run_in_background "scripts/port_forwarding_loop.sh $1 $2 $3"
}

function run_in_background() {
  bash -c "nohup $1  >/dev/null 2>&1 &"
}


function kill_portforwarding_loop() {
  kill -9 $(ps aux | grep "port_forwarding_loop.sh $1 $2 $3" | grep -v grep | awk '{print $2}') || true
  kill -9 $(ps aux | grep "kubectl --kubeconfig=${KUBECONFIG} port-forward | grep $3" | grep -v grep | awk '{print $2}') || true
}

function kill_all_port_forwardings() {
  kill -9 $(ps aux | grep "port_forwarding_loop" | grep -v grep | awk '{print $2}') || true
  kill -9 $(ps aux | grep "port-forward" | grep -v grep | awk '{print $2}') || true
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
      echo "Timeout reached, url not reachable"
      exit 1
    fi
}

"$@"