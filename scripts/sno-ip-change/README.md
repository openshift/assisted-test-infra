# SNO IP Change Tooling

This directory contains scripts to orchestrate an IP address change for a Single Node OpenShift (SNO) deployment in offline (disaster recovery) mode. It supports both single-stack and dual-stack clusters.

## Layout

- `flows/`:
  - `single-ip-change.sh`: Driver for single-stack clusters (IPv4 or IPv6).
  - `dual-ip-change.sh`: Driver for dual-stack clusters (IPv4+IPv6).
  - `secondary-ip-change.sh`: Driver to change the secondary IP on a dual-stack cluster (applies nmstate MC and reboots).
- `tests/`:
  - `test-single-ip-change.sh`: Helper that prepares the host, runs the flow, reboots the node, and verifies.
  - `test-dual-ip-change.sh`: Helper that prepares the host, runs the flow, reboots the node, and verifies.
  - `test-secondary-ip-change.sh`: Helper that prepares the host network, runs the secondary flow, and verifies.
- `remote/`:
  - `single-node-actions.sh`: On-node actions for single-stack.
  - `dual-node-actions.sh`: On-node actions for dual-stack.
  - `secondary-node-actions.sh`: On-node actions for secondary IP change (apply nmstate MC + first reboot).
- `lib/`: Function libraries (network, dns, crypto, recert, ssh, util, mc, cluster).

## Prerequisites

Common:
- Host has: bash, ssh, scp
- Node has: bash, podman, crictl, systemctl, base64, oc
- SSH access to the node as a user with sudo (defaults to `core`)

Offline specifics:
- Recert image saved to a tar file on the laptop (e.g., `recert-image.tar`); the script will load it on the node without pulling
- No external connectivity is required during the operation

## Usage

### Single-stack (flow)

```bash
scripts/sno-ip-change/flows/single-ip-change.sh \
  --old-ip 192.168.200.10 \
  --new-ip 192.168.201.20 \
  --new-machine-network 192.168.201.0/24 \
  --recert-image-tar /path/to/recert-image.tar
```

IPv6 single-stack example:

```bash
scripts/sno-ip-change/flows/single-ip-change.sh \
  --old-ip fd2e:6f44:5dd8:c956::10 \
  --new-ip fd2e:6f44:5dd8:c957::10 \
  --new-machine-network fd2e:6f44:5dd8:c957::/64 \
  --recert-image-tar /path/to/recert-image.tar
```

### Dual-stack (flow)

```bash
scripts/sno-ip-change/flows/dual-ip-change.sh \
  --old-ipv4 192.168.200.10 \
  --new-ipv4 192.168.201.20 \
  --new-machine-network-v4 192.168.201.0/24 \
  --old-ipv6 2001:db8::10 \
  --new-ipv6 2001:db8::20 \
  --new-machine-network-v6 2001:db8::/64 \
  --primary-stack v4 \
  --recert-image-tar /path/to/recert-image.tar
```

### Secondary IP change (flow)

Use this when you only need to change the secondary address on a dual-stack SNO (no recert image required):

```bash
scripts/sno-ip-change/flows/secondary-ip-change.sh \
  --old-secondary-ip 192.168.200.10 \
  --new-secondary-ip 192.168.201.20 \
  --new-machine-network 192.168.201.0/24 \
  --primary-ip 192.168.200.10
```

### Testing helpers

These helpers are convenient when your SNO node is a VM on the same host. They prepare host connectivity for the new machine network, call the appropriate flow, reboot the node, wait for SSH on the new IP, and verify cluster health.

Single-stack test:

```bash
scripts/sno-ip-change/tests/test-single-ip-change.sh \
  --old-ip 192.168.200.10 \
  --new-ip 192.168.201.20 \
  --new-machine-network 192.168.201.0/24 \
  --kubeconfig-path /path/to/kubeconfig \
  --recert-image-tar /path/to/recert-image.tar
```

IPv6 single-stack test example:

```bash
scripts/sno-ip-change/tests/test-single-ip-change.sh \
  --old-ip fd2e:6f44:5dd8:c956::10 \
  --new-ip fd2e:6f44:5dd8:c957::10 \
  --new-machine-network fd2e:6f44:5dd8:c957::/64 \
  --kubeconfig-path /path/to/kubeconfig \
  --recert-image-tar /path/to/recert-image.tar
```

Dual-stack test:

```bash
scripts/sno-ip-change/tests/test-dual-ip-change.sh \
  --old-ipv4 192.168.200.10 \
  --new-ipv4 192.168.201.20 \
  --new-machine-network-v4 192.168.201.0/24 \
  --old-ipv6 2001:db8::10 \
  --new-ipv6 2001:db8::20 \
  --new-machine-network-v6 2001:db8::/64 \
  --primary-stack v4 \
  --kubeconfig-path /path/to/kubeconfig \
  --recert-image-tar /path/to/recert-image.tar
```

Secondary IP change test:

```bash
scripts/sno-ip-change/tests/test-secondary-ip-change.sh \
  --old-secondary-ip 192.168.200.10 \
  --new-secondary-ip 192.168.201.20 \
  --new-machine-network 192.168.201.0/24 \
  --kubeconfig-path /path/to/kubeconfig \
  --primary-ip 192.168.200.10
```

### Notes

- Single-stack flows accept only three network-related flags: `--old-ip`, `--new-ip`, and `--new-machine-network` (IPv4 or IPv6 CIDR). Provide `--recert-image-tar` for offline operation.
- Dual-stack flows require both IPv4 and IPv6 sets with `--primary-stack` to select which stack to use for the initial SSH connection.
- Secondary IP flow accepts: `--old-ip`, `--new-ip`, `--new-machine-network`, and `--primary-ip` (the current primary address to SSH to) plus optional SSH params. The first reboot is executed on-node; the flow waits for the node to come up on the new IP and reboots again.
