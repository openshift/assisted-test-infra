source "${SHARED_DIR}/fix-uid.sh"
source "${SHARED_DIR}/ci-machine-config.sh"

export SSHOPTS=(-o 'ConnectTimeout=5' -o 'StrictHostKeyChecking=no' -o 'UserKnownHostsFile=/dev/null' -o 'ServerAliveInterval=90' -o LogLevel=ERROR -o 'ConnectionAttempts=10' -i "${SSH_KEY_FILE}")
