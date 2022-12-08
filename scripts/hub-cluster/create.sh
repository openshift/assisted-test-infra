#!/usr/bin/env bash

set -o nounset
set -o pipefail
set -o errexit
set -o xtrace

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case ${DEPLOY_TARGET} in
    minikube)
        $__dir/minikube.sh create
        ;;
    kind)
        $__dir/kind/kind.sh create
        ;;
    onprem)
        echo "onprem/podman requires no special setup"
        ;;
    *)
        echo "Unknown deploy target ${DEPLOY_TARGET}!";
        exit 1
        ;;
esac
