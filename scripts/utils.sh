#!/usr/bin/env bash

set -o nounset

export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
export NAMESPACE=${NAMESPACE:-assisted-installer}

function get_namespace_index() {
    namespace=$1
    oc_flag=${2:-}

    index=$(skipper run python3 scripts/indexer.py --action set --namespace $namespace $oc_flag)
    if [[ -z $index ]]; then
        all_namespaces=$(skipper run python3 scripts/indexer.py --action list)
        echo "Maximum number of namespaces allowed are currently running: $all_namespaces"
        echo "Please remove an old namespace in order to create a new one"
        exit 1
    fi

    echo $index
}

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
    namespace=$3
    namespace_index=$4
    kubeconfig=$5
    target=$6
    ip=${7:-""}
    port=${8:-""}
    xinet_service_name="${9:-${service_name}}"

    filename=${xinet_service_name}__${namespace}__${namespace_index}__${external_port}__assisted_installer
    if [ "$target" = "minikube" ]; then
        ip=$(kubectl --kubeconfig=$kubeconfig get nodes -o=jsonpath={.items[0].status.addresses[0].address})
        if [ -z "$port" ]
        then
          port=$(kubectl --kubeconfig=$kubeconfig get svc/${service_name} -n ${namespace} -o=jsonpath='{.spec.ports[0].nodePort}')
        else
          # resolve the service node port form the service internal port (Support multiple ports per service).
          port=$(kubectl --kubeconfig=$kubeconfig get svc/${service_name} -n ${namespace} -o=jsonpath="{.spec.ports[?(@.port==$port)].nodePort}")
        fi
    fi
    mkdir -p ./build
    cat <<EOF >build/xinetd-$filename
service ${xinet_service_name}
{
  type		= UNLISTED
  socket_type	= stream
  protocol	= tcp
  user		= root
  wait		= no
  redirect	= $ip $port
  port		= ${external_port}
  per_source	= UNLIMITED
  instances	= UNLIMITED
}
EOF
    sudo mv build/xinetd-$filename /etc/xinetd.d/$filename --force
    sudo systemctl restart xinetd
}

function run_in_background() {
    bash -c "nohup $1  >/dev/null 2>&1 &"
}

function kill_port_forwardings() {
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

function get_main_ip_v6() {
    echo "$(ip -6 route get ::ffff:100:0 | sed 's/^.*src \([^ ]*\).*$/\1/;q')"
}

function wait_for_url_and_run() {
    URL="$1"
    FUNCTION="$2"
    RETRIES=30
    RETRIES=$((RETRIES))

    until [ $RETRIES -eq 0 ]; do
        RETRIES=$((RETRIES - 1))

        echo "Running given function"
        ${FUNCTION}

        echo "Verifying URL and port are accessible"
        if url_reachable "${URL}"; then
          echo "URL ${URL} is reachable!"
          return
        fi

        echo "Sleeping for 2 seconds"
        sleep 2s
    done

    echo "Timeout reached, URL ${URL} is not reachable"
    exit 1
}

function close_external_ports() {
    ports=$1
    for p in $ports; do
        sudo firewall-cmd --zone=public --remove-port=$p/tcp
    done
}

function add_firewalld_port() {
    port=$1
    if [ "${EXTERNAL_PORT}" = "y" ]; then
        echo "configuring external ports"
        sudo firewall-cmd --zone=public --add-port=$port/tcp
    fi
    echo "configuring libvirt zone ports ports"
    sudo firewall-cmd --zone=libvirt --add-port=$port/tcp
}

function as_singleton() {
    func=$1
    interval=${2:-15s}

    lockfile=/tmp/$func.lock

    while [ -e "$lockfile" ]; do
        echo "Can run only one instance of $func at a time..."
        echo "Waiting for other instances of $func to be completed..."
        sleep $interval
    done

    trap 'rm "$lockfile"; exit' EXIT INT TERM HUP
    touch $lockfile

    $func
}


function validate_namespace() {
    namespace=$1
    if [[ $namespace =~ ^[0-9a-zA-Z\-]+$ ]]; then
        return
    fi
    echo "Invalid namespace '$namespace'"
    echo "It can contain only letters, numbers and '-'"
    exit 1
}

function running_from_skipper() {
   # The SKIPPER_UID environment variable is an indication that we are running on a skipper container.
   [ -n "${SKIPPER_UID+x}" ]
}

function get_container_runtime_command() {
  # if CONTAINER_TOOL is defined skipping
  if [ -z "${CONTAINER_TOOL+x}" ]; then
    if running_from_skipper; then
      if [ -z ${CONTAINER_RUNTIME_COMMAND+x} ]; then
        echo "CONTAINER_RUNTIME_COMMAND doesn't set on old skipper version -> default to podman. Upgrade your skipper to the latest version" 1>&2;
      fi

      if [ "${CONTAINER_RUNTIME_COMMAND:-podman}" = "docker" ]; then
        CONTAINER_TOOL="docker"
      else
        CONTAINER_TOOL=$( command -v podman &> /dev/null && echo "podman" || echo "podman-remote")
      fi
    else
      # The Docker command could be an alias for podman, so check first for podman
      # Fallback to Docker if podman is not available
      # In the absence of a container tool installed on the system, default to podman as we will install it during setup.
      CONTAINER_TOOL=$( command -v podman &> /dev/null && echo "podman" || (command -v docker &> /dev/null && echo "docker" || echo "podman"))
    fi
  fi

  echo $CONTAINER_TOOL
}

# podman-remote4 cannot run against podman server 3 so the skipper image contains them both
# here we select the right podman-remote version
function select_podman_client() {
  # already linked
  if command -v podman-remote &> /dev/null; then
    exit
  fi

  if [ "$(get_container_runtime_command)" = "podman-remote" ]; then
    if podman-remote4 info 2>&1 | grep "server API version is too old" &> /dev/null; then
      echo "using podman-remote version 3"
      ln $(which podman-remote3) /tools/podman-remote
    else
      echo "using podman-remote version 4"
      ln $(which podman-remote4) /tools/podman-remote
    fi
  fi
}

"$@"
