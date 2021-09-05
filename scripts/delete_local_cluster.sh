#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

readonly DEFAULT_CLUSTER_NAME="assisted-test"
readonly DEFAULT_REGISTRY_NAME="local-registry"

k3d cluster delete "${DEFAULT_CLUSTER_NAME}"
container_hash="$(${CONTAINER_COMMAND} ps -q -f name="${DEFAULT_REGISTRY_NAME}" 2>/dev/null || true)"
if [ -z "${container_hash}" ]; then
  echo "Container ${DEFAULT_REGISTRY_NAME} does not exist, skipping cleaning up."
  exit 0
fi
echo "Deleting container ${DEFAULT_REGISTRY_NAME}"
${CONTAINER_COMMAND} container stop "${DEFAULT_REGISTRY_NAME}"
${CONTAINER_COMMAND} container rm "${DEFAULT_REGISTRY_NAME}"
