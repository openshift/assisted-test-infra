#!/bin/bash

SOS_TMPDIR="/var/tmp"

# cleanup any previous sos report
find "${SOS_TMPDIR}" -maxdepth 1 -name "sosreport*" -type f -delete

podman pull \
  --authfile /run/user/0/containers/auth.json \
  registry.redhat.io/rhel8/support-tools
toolbox sos report --batch --tmp-dir "${SOS_TMPDIR}" --compression-type xz --all-logs \
                   --plugin-timeout=300 \
                   -o processor,memory,container_log,filesys,logs,crio,podman,openshift,openshift_ovn,networking,networkmanager,rhcos \
                   -k crio.all=on -k crio.logs=on \
                   -k podman.all=on -k podman.logs=on \
                   -k openshift.with-api=on

# rename the sosreport archive with a deterministic name in order to download it afterwards
find "${SOS_TMPDIR}" -maxdepth 1 -name "sosreport*.tar.xz" -type f -execdir mv {} "${SOS_TMPDIR}/sosreport.tar.xz" \;
chmod a+r "${SOS_TMPDIR}/sosreport.tar.xz"
