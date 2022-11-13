#!/usr/bin/env bash

set -o nounset
set -o pipefail
set -o errexit
set -o xtrace

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case ${DEPLOY_TARGET} in
    minikube)
        $__dir/minikube.sh delete
        ;;
    kind)
        $__dir/kind/kind.sh delete
        ;;
    *)
        echo "Unknown deploy target ${DEPLOY_TARGET}!";
        exit 1
        ;;
esac
