#!/usr/bin/env bash

cat > /usr/bin/install_complete.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail

export HOME=/root

### Status flag
LOGFILE=/root/ibmcloud-post-install.log
log () {
  echo "\$(date) +++ \$1" >> \$LOGFILE
}

log "Starting ibmcloud-post-install.sh"

### Check if the script has been already run
if [ -f /root/ibmcloud-post-install.log ]; then
    log "Found existing log, exiting !"
    exit 0
fi

{
### Base prerequisites
dnf install -y git

### Get AI repo
mkdir -p /home/test
cd /home/test
git clone https://github.com/openshift/assisted-test-infra.git

### Provision test-infra
cd /home/test/assisted-test-infra

scripts/install_environment.sh
scripts/install_environment.sh config_sshd

} &>> \$LOGFILE

### Status flag
log "Finished ibmcloud-post-install.sh, thank you !"
EOF
chmod 755 /root/install_complete.sh

# set timeoutsec explicitly to prevent timeout fail
# ref. https://qiita.com/khayama/items/861243aed5cf95f318d1
cat > /etc/systemd/system/install_complete.service <<EOF
[Unit]
Description=INSTALL_COMPLETE
After=network.target
[Service]
ExecStart=/usr/bin/install_complete.sh
Type=oneshot
TimeoutSec=infinity
[Install]
WantedBy=multi-user.target
EOF

# run your script above without timeout fail bug
systemctl daemon-reload
systemctl restart install_complete.service
