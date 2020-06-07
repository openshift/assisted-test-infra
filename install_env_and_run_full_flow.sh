#!/usr/bin/env bash

source create_full_environment.sh
retVal=$?
if [ $retVal -ne 0 ]; then
  exit $retVal
fi

source scripts/assisted_deployment.sh

echo "Starting cluster"
export SET_DNS="y"
export CLUSTER_NAME=${CLUSTER_NAME:-"test-infra-cluster"}
run_without_os_envs "run_full_flow_with_install" && set_dns
