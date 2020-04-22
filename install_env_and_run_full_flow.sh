#!/usr/bin/env bash

source create_full_environment.sh

echo "Starting cluster"
/usr/local/bin/skipper make run_full_flow_with_install
