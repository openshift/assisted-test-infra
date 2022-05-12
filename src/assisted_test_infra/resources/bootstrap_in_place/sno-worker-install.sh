#!/bin/bash

set -euxo pipefail

if coreos-installer install --ignition=/root/config.ign ${INSTALL_DEVICE}; then
	echo "Worker OS installation succeeded!"
else
	echo "Worker OS installation failed!"
	exit 1
fi

reboot
