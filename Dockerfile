FROM quay.io/centos/centos:stream9 AS IMAGE

ARG TARGETPLATFORM

ENV TOOLS=/tools/
ENV PATH="$TOOLS:$PATH"
RUN mkdir $TOOLS --mode g+xw

# TODO: Remove once OpenShift CI supports it out of the box (see https://access.redhat.com/articles/4859371)

RUN chmod g+w /etc/passwd && \
    echo 'echo default:x:$(id -u):$(id -g):Default Application User:/alabama:/sbin/nologin\ >> /etc/passwd' > /usr/local/bin/fix_uid.sh && \
    chmod g+rwx /usr/local/bin/fix_uid.sh

RUN  <<EOR
    cat <<EOF >>  /etc/dnf/dnf.conf
fastestmirror=1
max_parallel_downloads=10
EOF
EOR

RUN dnf -y install --enablerepo=crb \
  make gcc unzip curl-minimal git httpd-tools jq nss_wrapper \
  libvirt-client guestfs-tools libvirt-devel libguestfs-tools libxslt \
  xorriso iptables-nft && dnf clean all


FROM registry.access.redhat.com/ubi9/go-toolset:1.21 AS download

ARG TARGETPLATFORM
ENV OPTS="--retry 2 --connect-timeout 30 -sL"

WORKDIR /opt/downloads

RUN PLATFORM=$(echo ${TARGETPLATFORM} | cut -d"/" -f2) && \
    echo $PLATFORM && \
    curl -sL "https://releases.hashicorp.com/packer/1.10.1/packer_1.10.1_linux_$PLATFORM.zip" | zcat >> packer



FROM IMAGE as Final

  COPY --from=download /opts/downloads /usr/local/
