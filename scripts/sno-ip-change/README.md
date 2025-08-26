# SNO IPv4 Change Tooling

This directory contains scripts to orchestrate an IP address change for a Single Node OpenShift (SNO) deployment.

## Components

- ip-change.sh: Main orchestrator run from the host controlling the SNO node.
- remote/node-actions.sh: Node-side actions executed over SSH with root privileges.
- test-ip-change.sh: Optional helper for testing when SNO runs as a VM on the host. Adds a host-side helper IP to reach the new subnet, then invokes ip-change.sh.
- lib/: Function libraries used by the scripts (network, dns, crypto, recert, ssh, util, mc, cluster).

## Prerequisites

- Host has: bash, oc, jq, ssh, scp, base64
- Node has: bash, podman, crictl, systemctl, base64
- Pull-secret is available on the host
- Kubeconfig (external) is available on the host

## Usage

Basic flow:

```bash
sudo scripts/sno-ip-change/ip-change.sh \
  --old-ip 192.168.200.10 \
  --new-ip 192.168.201.20 \
  --new-machine-network 192.168.201.0/24 \
  --pull-secret-path ~/.pull-secret.json \
  --kubeconfig-path ~/.kube/config
```

Testing helper (VM on the host):

```bash
scripts/sno-ip-change/test-ip-change.sh --dev tt6 \
  --old-ip 192.168.200.10 --new-ip 192.168.201.20 \
  --pull-secret-path ~/.pull-secret.json --kubeconfig-path ~/.kube/config
```
