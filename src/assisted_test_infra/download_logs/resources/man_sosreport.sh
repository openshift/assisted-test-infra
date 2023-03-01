#!/bin/bash

SOS_TMPDIR="/var/tmp"
PROXY_SETTING_FILE="/etc/mco/proxy.env"

TOOLBOX_BIN="toolbox"
TOOLBOX_VERSION="$(rpm -q --queryformat '%{VERSION}' toolbox)"
TOOLBOX_MIN_VERSION="0.1.0"

# setup proxy environment variables
if [ -f "${PROXY_SETTING_FILE}" ]
then
  # shellcheck source=/dev/null
  source "${PROXY_SETTING_FILE}"
  export HTTP_PROXY
  export HTTPS_PROXY
  export NO_PROXY
fi

# check if toolbox version is above or equal to 0.1.0 (it should be the case for OCP>=4.11)
# previous versions of toolbox run a shell instead of command specified in parameter
if ! echo -e "${TOOLBOX_MIN_VERSION}\n${TOOLBOX_VERSION}" | sort --version-sort --check=silent; then
  # fallback on the upstream version of toolbox
  curl -o /tmp/toolbox "https://raw.githubusercontent.com/coreos/toolbox/${TOOLBOX_MIN_VERSION}/rhcos-toolbox"
  chmod +x /tmp/toolbox
  TOOLBOX_BIN="/tmp/toolbox"
fi

# cleanup any previous sos report
find "${SOS_TMPDIR}" -maxdepth 1 -name "sosreport*" -type f -delete

yes | ${TOOLBOX_BIN} sos report --batch --tmp-dir "${SOS_TMPDIR}" --compression-type xz --all-logs \
                   --plugin-timeout=300 \
                   -o processor,memory,container_log,filesys,logs,crio,podman,openshift,openshift_ovn,networking,networkmanager,rhcos \
                   -k crio.all=on -k crio.logs=on \
                   -k podman.all=on -k podman.logs=on \
                   -k openshift.with-api=on

# rename the sosreport archive with a deterministic name in order to download it afterwards
find "${SOS_TMPDIR}" -maxdepth 1 -name "sosreport*.tar.xz" -type f -execdir mv {} "${SOS_TMPDIR}/sosreport.tar.xz" \;
chmod a+r "${SOS_TMPDIR}/sosreport.tar.xz"
