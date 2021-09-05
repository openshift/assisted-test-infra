#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

readonly DEFAULT_CLUSTER_NAME="assisted-test"

function generate_config_file() {
    tee << EOF "${HOME}/.test-infra/k3d_config"
apiVersion: k3d.io/v1alpha2
kind: Simple
name: ${DEFAULT_CLUSTER_NAME}
servers: 1
registries:
  create: true
  config: |
    mirrors:
      "localhost":
        endpoint:
          - http://localhost:5000
options:
  k3d:
    wait: true
EOF
}

function setup_cluster() {
    k3d cluster create --config="${HOME}/.test-infra/k3d_config"
}

if ! kubectl cluster-info; then
    generate_config_file
    setup_cluster
fi
