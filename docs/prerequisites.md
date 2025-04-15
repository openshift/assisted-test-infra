# Prerequisites

- CentOS 9 / RHEL 9 / Rocky 9 / AlmaLinux 9 host
- File system that supports d_type
- Ideally on a bare metal host with at least 64G of RAM.
- Run as a user with password-less `sudo` access or be ready to enter `sudo` password for prepare phase.
- Make sure to unset the KUBECONFIG variable in the same shell where you run `make`.
- install git & make binaries:
    ```bash
    dnf install -y make git
    ```
- Generate ssh keys if missing:
    ```bash
    ssh-keygen -t rsa -f ~/.ssh/id_rsa -P ''
    ```
- Get a valid pull secret (JSON string) from [redhat.com](https://console.redhat.com/openshift/install/pull-secret) if you want to test the installation (not needed for testing only the discovery flow). Export it as:
    ```bash
    export PULL_SECRET='<pull secret JSON>'
    # or alternatively, define PULL_SECRET_FILE="/path/to/pull/secret/file"
    ```