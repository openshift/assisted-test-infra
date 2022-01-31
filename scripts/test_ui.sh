#!/usr/bin/env bash
set -euo pipefail

source scripts/utils.sh

export NO_UI=${NO_UI:-n}
if [ "${NO_UI}" != "n" ]; then
    exit 0
fi

export NODE_IP=$(get_main_ip)
export UI_PORT=${UI_PORT:-6008}
export DEPLOY_TAG=${DEPLOY_TAG:-latest}
export CYPRESS_BASE_URL=${CYPRESS_BASE_URL:-http://${NODE_IP}:${UI_PORT}} # URL of running Metal3 Installer UI
export TESTS_IMAGE=${TESTS_IMAGE:-"quay.io/edge-infrastructure/assisted-installer-ui:${DEPLOY_TAG}"}
export CONTAINER_COMMAND=${CONTAINER_COMMAND:-podman}
export BASE_DIR=${BASE_DIR:-"$(pwd)"/$(date +%D_%T | sed 's/\//_/g' | sed 's/:/-/g')} # where screenshots will be stored

if [ "${CONTAINER_COMMAND}" = "podman" ]; then
    export PODMAN_FLAGS="--pull=always"
else
    export PODMAN_FLAGS=""
fi

echo Connecting to UI at: ${CYPRESS_BASE_URL}
echo Test image: ${TESTS_IMAGE}

export VIDEO_DIR=${BASE_DIR}/videos
export SCREENSHOT_DIR=${BASE_DIR}/screenshots

mkdir -p ${VIDEO_DIR}
mkdir -p ${SCREENSHOT_DIR}

${CONTAINER_COMMAND} run -it \
    -w /e2e \
    -e CYPRESS_BASE_URL="${CYPRESS_BASE_URL}" \
    -e CYPRESS_PULL_SECRET="${PULL_SECRET}" \
    --security-opt label=disable \
    --mount type=bind,source=${VIDEO_DIR},target=/e2e/cypress/videos \
    --mount type=bind,source=${SCREENSHOT_DIR},target=/e2e/cypress/screenshots \
    "${TESTS_IMAGE}"

echo Screenshots and videos can be found in ${BASE_DIR}
