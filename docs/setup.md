## Setup

`make setup` performs all of the operations required to take a fresh machine and prepare it for test infra operations. It performs three main operations to prepare the machine for running all available flows:

### 1. Installing Dependencies

The setup script installs the following packages and tools to prepare the system:

#### System Packages (via `dnf`)

- `make`: For automating command execution and scripting.
- `python3` and `python3-pip`: Python runtime and package manager.
- `git`: Source control and cloning repositories.
- `jq`: Lightweight command-line JSON processor.
- `bash-completion`: Tab-completion for common CLI tools.
- `libvirt`, `qemu-kvm`, `libvirt-devel`, `libvirt-daemon-kvm`: For virtualization and VM management.
- `swtpm`, `swtpm-tools`: Software TPM for virtualized environments.
- `socat`: For TCP and UNIX socket forwarding.
- `tigervnc-server`: Remote graphical access to virtual machines.
- `virt-install`: For managing libvirt-based VM creation.
- `firewalld`: System firewall.
- `squid`: HTTP proxy server for testing.
- `chrony`: NTP client/server for time synchronization.

#### Python Packages (via `pip3`)

- `pip` (upgraded to latest)
- `aicli`: CLI for interacting with the Assisted Installer deployment.
- `strato-skipper==2.0.2`: Utility to run commands inside containers.

> The script ensures that `skipper` is installed and available in the system path (`/usr/local/bin`) if not found in the default user binary directory (`~/.local/bin`).

#### Container Runtime

- Installs `podman` (version >= 3.2.0 required).
- If Docker is already installed, Podman installation is skipped.
- Cleans up stale podman state (`/run/user/<UID>/podman` and `/run/podman`).
- Enables and starts the `podman.socket` for system and user sessions.
- Configures `loginctl enable-linger` for persistent user services.

> If `podman` is installed but the version is too old, the script will warn and proceed.

### 2. Configuring Package Settings

#### `dnf`

- Adds `fastestmirror=1` for quicker mirror selection.
- Adds `max_parallel_downloads=10` to speed up installations.

#### Additional Modules

- Enables the EPEL repository for access to extra packages.
- Enables `container-tools` module stream for Podman 4.0 on RHEL/CentOS 8.

#### `libvirt`

- Installs the full `libvirt` stack including `libvirt`, `qemu-kvm`, `swtpm`, `tigervnc`, etc.
- Adds the current user to `libvirt` and `qemu` groups for management permissions.
- Adjusts `libvirtd.conf` and `qemu.conf` to enable TCP listening and non-SELinux isolation.
- Handles both older and newer `libvirt` versions:
  - For versions < 5.5: adds `--listen` systemd flag.
  - For versions >= 5.5: enables the `libvirtd-tcp.socket`.
- Applies a `libvirt` network hook to allow cross-network traffic between guest networks.
- **Automatically reactivates the default `libvirt` network if found inactive.**
- **Enables additional system ports:**
  - Ports `59151–59154` for virtual console/VNC
  - Port `8500` for iPXE boot
  - Port `7500` for Tang server (used in disk encryption workflows)

#### `firewalld`

- Installs and starts `firewalld`.
- Ensures `libvirtd` reloads and configures:
  - Port `123` for `chronyd` (UDP)
  - Ports `3128` and `3129` for `squid` (TCP)
  - Ports `6443`, `22623`, `443`, and `80` for `nginx` (TCP)
  - Additional ports (above) for VNC, iPXE, and Tang use cases

#### `squid`

- Configures IPv6-based access rules.
- Opens ports `3128` and `3129` in the `libvirt` firewall zone.

#### `IPv6`

- Enables IPv6 system-wide (if it was disabled).
- Ensures `net.ipv6.conf.<iface>.accept_ra = 2` for all real interfaces.
- Appends a dispatcher script to reapply settings on interface changes.
- Tunes kernel network performance by setting `net.core.somaxconn = 2000`.

#### `chronyd`

- Removes existing NTP server entries and replaces them with a local authoritative NTP server.
- Allows incoming NTP connections from `libvirt` guests.
- Opens UDP port `123` in the firewall.

#### `nginx`

- Removes any existing `load_balancer` container.
- Creates required `nginx` configuration structure under:
  - `~/.test-infra/etc/nginx/conf.d/{stream,http}.d`
- Opens the following ports in the `libvirt` zone:
  - `6443`: Kubernetes API server
  - `22623`: OpenShift ignition server
  - `443`, `80`: HTTPS/HTTP endpoints

#### `sshd`

- Enforces `PubkeyAuthentication = yes`
- Disables `PasswordAuthentication = no`
- Restarts the `sshd` service

#### Additional System Configuration

- Optionally enables **passwordless sudo access** for the current user (when `ADD_USER_TO_SUDO=y`)
- Creates a `.gitconfig` file (if not present) to prevent Git-related tooling errors.
- Adjusts **directory permissions** for parent folders to ensure playbooks and tools can traverse the file hierarchy.
- Sets **SELinux to permissive mode** to reduce policy rejections during development.
- Generates an **SSH RSA keypair** in `~/.ssh/id_rsa` if none exists, with appropriate permissions.

### 3. Creating assisted service python client and building skipper image

See description [here](./build-image.md)
