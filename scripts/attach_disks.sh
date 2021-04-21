#!/usr/bin/env bash

set -o nounset
set -o pipefail
set -o errexit

function clear_disks() {
    nodes=$(virsh list --name | grep worker || virsh list --name | grep master)
    for node in ${nodes}; do
        for disk in sd{b..c}; do
            img_path="/tmp/${node}-${disk}.img"
            if [ -f ${img_path} ]; then
                virsh detach-disk "${node}" "${disk}"
                rm -rf ${img_path}
            fi
        done
    done

    kubectl get pv -o=name | xargs -r kubectl delete
}

function attach_disks() {
    echo "Creating disks..."
    nodes=$(virsh list --name | grep worker || virsh list --name | grep master)
    for node in ${nodes}; do
        for disk in sd{b..c}; do
            img_path="/tmp/${node}-${disk}.img"
            if [ ! -f ${img_path} ]; then
                qemu-img create -f raw ${img_path} 50G
                virsh attach-disk "${node}" ${img_path} "${disk}"
            fi
        done
    done

    echo "Waiting for LocalVolume CDR to become ready..."
    kubectl -n openshift-local-storage wait --for condition=established --timeout=60s crd/localvolumes.local.storage.openshift.io

    echo "Creating local volume and storage class..."
    cat << EOF | kubectl apply -f -
apiVersion: local.storage.openshift.io/v1
kind: LocalVolume
metadata:
  name: assisted-service
  namespace: openshift-local-storage
spec:
  logLevel: Normal
  managementState: Managed
  storageClassDevices:
    - devicePaths:
        - /dev/sdb
        - /dev/sdc
      fsType: ext4
      storageClassName: localblock-sc
      volumeMode: Filesystem
EOF
}

"$@"
