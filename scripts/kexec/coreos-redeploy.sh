#! /bin/sh -e

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root"
    exit 1
fi

ISO_URL=$1
MOUNT='mount -o loop,ro image'
KERNEL='images/vmlinuz'
INITRD='images/initramfs.img'
KERNEL_ARG='mitigations=auto,nosmt systemd.unified_cgroup_hierarchy=0 coreos.liveiso=fedora-coreos-31.20200319.dev.1 rd.neednet=1 ip=dhcp ignition.firstboot ignition.platform.id=metal'
KEXEC_PATH='/usr/local/bin'
KEXEC_IMG='quay.io/ohadlevy/kexec'

podman run --privileged --rm -v $KEXEC_PATH:/hostbin $KEXEC_IMG cp /kexec /hostbin

TMP=$(mktemp -d)

cd $TMP
mkdir mnt
curl -O $ISO_URL
$MOUNT mnt && cd mnt

printf '%s %s\n' "$(date)" "$line"
echo kexecing $(hostname)... rebooting.

$KEXEC_PATH/kexec --force --initrd=$INITRD --append="$KERNEL_ARG" $KERNEL
