#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

readonly DEFAULT_REGISTRY_NAME="local-registry"
readonly DEFAULT_REGISTRY_PORT="5000"

# create registry container unless it already exists
running="$(${CONTAINER_COMMAND} inspect -f '{{.State.Running}}' "${DEFAULT_REGISTRY_NAME}" 2>/dev/null || true)"
if [ "${running}" != 'true' ]; then
  echo "Creating ${CONTAINER_COMMAND} container for hosting local registry localhost:${DEFAULT_REGISTRY_PORT}"
  ${CONTAINER_COMMAND} run \
    -d --restart=always -p "127.0.0.1:${DEFAULT_REGISTRY_PORT}:${DEFAULT_REGISTRY_PORT}" --name "${DEFAULT_REGISTRY_NAME}" \
    registry:2
else
  echo "Local registry localhost:${DEFAULT_REGISTRY_PORT} already exist and running."
fi
