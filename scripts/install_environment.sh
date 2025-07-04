#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export EXTERNAL_PORT=${EXTERNAL_PORT:-true}
export ADD_USER_TO_SUDO=${ADD_USER_TO_SUDO:-n}
readonly PODMAN_MINIMUM_VERSION="3.2.0"

function version_is_greater() {
    if [ "$(head -n1 <(printf '%s\n' "$2" "$1" | sort -V))" = "$2" ]; then
        return
    fi
    echo "$(head -n1 <(printf '%s\n' "$2" "$1" | sort -V))"
    false
}

function config_additional_modules() {
    source /etc/os-release # This should set `PRETTY_NAME` as environment variable

    case "${PRETTY_NAME}" in
    "Red Hat Enterprise Linux 8"* | "CentOS Linux 8"*)
        echo "Enable EPEL for swtpm packages when on RHEL/CentOS based distributions"
        sudo dnf install -y \
            https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm

        echo "Enable podman 4.0 stream for newer podman versions"
        sudo dnf module reset -y container-tools
        sudo dnf module enable -y container-tools:4.0
        sudo dnf module install -y container-tools:4.0
        ;;

    "Red Hat Enterprise Linux 9"* | "CentOS Linux 9"*)
        echo "Enable EPEL for swtpm packages when on RHEL/CentOS based distributions"
        sudo dnf install -y \
            https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
        dnf install podman -y
        ;;

    *)
        echo "Enable EPEL for swtpm packages"
        sudo dnf install -y epel-release
    esac
}

function install_libvirt() {
    echo "Installing libvirt-related packages..."

    source /etc/os-release
    if [[ "${PRETTY_NAME}" =~ "Rocky Linux 9" ]]; then
      # workaround where libvirt cannot be installed
      # with iptables
      sudo dnf remove -y iptables
    fi

    # CRB repo is required for libvirt-devel in some versions of RHEL
    sudo dnf install -y 'dnf-command(config-manager)' || true
    sudo dnf config-manager --set-enabled crb || true
    sudo dnf install -y \
        libvirt \
        libvirt-devel \
        libvirt-daemon-kvm \
        qemu-kvm \
        libgcrypt \
        swtpm \
        swtpm-tools \
        socat \
        tigervnc-server

    sudo systemctl enable libvirtd

    current_version="$(libvirtd --version | awk '{print $3}')"
    minimum_version="5.5.100"

    echo "Setting libvirt values"
    sudo sed -i -e 's/#listen_tls/listen_tls/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#listen_tcp/listen_tcp/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#auth_tcp = "sasl"/auth_tcp = "none"/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#tcp_port/tcp_port/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#security_driver = "selinux"/security_driver = "none"/g' /etc/libvirt/qemu.conf

    allow_libvirt_cross_network_traffic

    if ! version_is_greater "$current_version" "$minimum_version"; then
        add_libvirt_listen_flag
    else
        sudo dnf upgrade -y libgcrypt
        start_and_enable_libvirtd_tcp_socket
    fi

    current_user=$(whoami)
    echo "Adding user ${current_user} to libvirt and qemu groups"
    sudo gpasswd -a $current_user libvirt
    sudo gpasswd -a $current_user qemu
}

function install_virt_install() {
    echo "Installing virt-install for remote libvirt access..." 
    sudo dnf install -y virt-install
}

function add_libvirt_listen_flag() {
    if [[ -z $(sudo grep '#LIBVIRTD_ARGS="--listen"' /etc/sysconfig/libvirtd) ]]; then
        return
    fi
    echo "Adding --listen flag to libvirt"
    sudo sed -i -e 's/#LIBVIRTD_ARGS="--listen"/LIBVIRTD_ARGS="--listen"/g' /etc/sysconfig/libvirtd
    sudo systemctl restart libvirtd
}

function start_and_enable_libvirtd_tcp_socket() {
    if [[ $(is_libvirtd_tcp_socket_enabled_and_running) == "true" ]]; then
        return
    fi
    echo "libvirtd version is greater then 5.5.x, starting libvirtd-tcp.socket"
    echo "Removing --listen flag to libvirt"
    
    OS_VERSION=$(awk -F= '/^VERSION_ID=/ { print $2 }' /etc/os-release | tr -d '"' | cut -f1 -d'.')
    if [[ "${OS_VERSION}" ==  "8" ]]; then
        sudo sed -i -e 's/LIBVIRTD_ARGS="--listen"/#LIBVIRTD_ARGS="--listen"/g' /etc/sysconfig/libvirtd
    fi

    sudo systemctl stop libvirtd
    sudo systemctl unmask libvirtd-tcp.socket
    sudo systemctl unmask libvirtd.socket
    sudo systemctl unmask libvirtd-ro.socket
    sudo systemctl restart libvirtd.socket
    sudo systemctl enable --now libvirtd-tcp.socket
    sudo systemctl start libvirtd
}

function is_libvirtd_tcp_socket_enabled_and_running() {
    libvirtd_tcp_status=$(sudo systemctl status libvirtd-tcp.socket)
    if [[ -z $(echo $libvirtd_tcp_status | grep running) ]]; then
        echo "false"
    elif [[ -z $(echo $libvirtd_tcp_status | grep enabled) ]]; then
        echo "false"
    else
        echo "true"
    fi
}

function allow_libvirt_cross_network_traffic() {
    # Remove Reject rules from LIBVIRT_FWI and LIBVIRT_FWO chains each time the network
    # configuration is being updated by libvirt.
    #
    # By default, LIBVIRT_FWI chain managed by libvirt denies the traffic
    # between guest networks, flushing it makes this traffic possible.
    #
    # It is required in order to let a cluster being installed to contact the
    # HUB cluster located in another libvirt network (e.g.: to retrieve the
    # rootfs).
    echo "Installing libvirt network hook to allow cross network traffic"

    hook_src="${SCRIPT_DIR}/../ansible_files/roles/setup_libvirtd/files/allow-cross-network-traffic.sh"

    hook_dir="/etc/libvirt/hooks/network.d"
    hook_filename="${hook_dir}/allow-cross-network-traffic.sh"
    sudo mkdir -p "${hook_dir}"

    sudo cp "${hook_src}" "${hook_filename}"
    sudo chmod +x "${hook_filename}"
}

function install_podman(){
    sudo systemctl disable --now podman.socket || true
    sudo rm -rf /run/user/${UID}/podman
    sudo rm -rf /run/podman
    sudo dnf install --best podman -y
    sudo systemctl enable --now podman.socket
    systemctl --user enable --now podman.socket
    sudo loginctl enable-linger $USER
}

function install_runtime_container() {
    echo "Container runtime package"
    if [ -x "$(command -v docker)" ]; then
        echo "docker is already installed"
        return
    fi

    # getting podman version and allowing it to fail if podman is not installed
    current_podman_version="$(podman info --format={{.Version.Version}} || true)"

    if [ -n "${current_podman_version}" ] && \
            version_is_greater "${current_podman_version}" "${PODMAN_MINIMUM_VERSION}" && \
            systemctl is-active --quiet podman.socket; then
        echo "podman is already installed and version is greater than ${PODMAN_MINIMUM_VERSION}"
        return
    fi

    install_podman

    # recalculating the version again to see if it got upgraded
    current_podman_version="$(podman info --format={{.Version.Version}})"
    if ! version_is_greater "${current_podman_version}" "${PODMAN_MINIMUM_VERSION}"; then
        echo >&2 "podman version ($current_podman_version) is older than ($PODMAN_MINIMUM_VERSION) and might not work as expected"
    fi
}

function install_packages() {
    echo "Installing dnf packages"
    sudo dnf install -y make python3 python3-pip git jq bash-completion

    echo "Installing python packages"
    sudo pip3 install -U pip
    sudo pip3 install aicli
}

function install_skipper() {
    echo "Installing skipper and adding ~/.local/bin to PATH"
    pip3 install strato-skipper==2.0.2 --user

    #grep -qxF "export PATH=~/.local/bin:$PATH" ~/.bashrc || echo "export PATH=~/.local/bin:$PATH" >> ~/.bashrc
    #export PATH="$PATH:~/.local/bin"

    if ! [ -x "$(command -v skipper)" ]; then
        sudo cp ~/.local/bin/skipper /usr/local/bin
    fi
}

function config_firewalld() {
    echo "Config firewall"
    sudo dnf install -y firewalld
    sudo systemctl unmask --now firewalld
    sudo systemctl start firewalld

    # Restart to see we are using firewalld
    sudo systemctl restart libvirtd
}

function config_squid() {
    echo "Config squid"
    sudo dnf install -y squid

    OS_VERSION=$(awk -F= '/^VERSION_ID=/ { print $2 }' /etc/os-release | tr -d '"' | cut -f1 -d'.')
    if [[ "${OS_VERSION}" ==  "8" ]]; then
        sudo sed -i  -e '/^.*allowed_ips.*$/d' \
            -e '/^acl CONNECT.*/a acl allowed_ips src 1001:db8::/120' \
            -e '/^acl CONNECT.*/a acl allowed_ips src 1001:db8:0:200::/120' \
            -e '/^http_access deny all/i http_access allow allowed_ips' /etc/squid/squid.conf
    else
        sudo sed -i -e '/^.*allowed_ips.*$/d' \
            -e '/^acl Safe_ports port 777/a acl allowed_ips src 1001:db8::/120\nacl allowed_ips src 1001:db8:0:200::/120' \
            -e '/^http_access deny all/i http_access allow allowed_ips' /etc/squid/squid.conf
    fi

    sudo systemctl restart squid
    sudo firewall-cmd --zone=libvirt --add-port=3128/tcp
    sudo firewall-cmd --zone=libvirt --add-port=3129/tcp
}

function fix_ipv6_routing() {
  sudo sed -i '/^net[.]ipv6[.]conf[.][^.]*[.]accept_ra = 2$/d' /etc/sysctl.conf
  for intf in `ls -l /sys/class/net/ | grep root | grep -v virtual | awk '{print $9}'` ; do
      if sudo test ! -f "/proc/sys/net/ipv6/conf/${intf}/accept_ra"; then
          echo "WARNING: It looks like IPv6 is disabled for this interface and might not work"
          continue
      fi
      echo "net.ipv6.conf.${intf}.accept_ra = 2" | sudo tee --append /etc/sysctl.conf
  done
  sudo sysctl --load
  fname=/etc/NetworkManager/dispatcher.d/40-sysctl-load.sh
  sudo tee $fname <<EOF
#! /bin/bash
sysctl --load
EOF
  sudo chmod +x $fname
}

function config_chronyd() {
  echo "Config chronyd"
  sudo dnf install -y chrony
  sudo sed -i -e '/^[ \t]*server[ \t]/d' -e '/allow[ \t]*$/d' -e '/^[ \t]*local stratum/d' -e '/^[ \t]*manual[ \t]*$/d' /etc/chrony.conf
  sudo sed -i -e '$a allow' -e '$a manual' -e  '$a local stratum 10' /etc/chrony.conf
  sudo systemctl restart chronyd.service || systemctl status --no-pager chronyd.service
  sudo firewall-cmd --zone=libvirt --add-port=123/udp
}

function config_nginx() {
  echo "Config nginx"

  # Configure a container to be used as the load balancer.
  # Initially, it starts nginx that opens a stream includes all conf files
  # in directory /etc/nginx/conf.d. The nginx is refreshed every 60 seconds
  podman rm -f load_balancer --ignore
  sudo mkdir -p $HOME/.test-infra/etc/nginx/conf.d/{stream,http}.d
  sudo firewall-cmd --zone=libvirt --add-port=6443/tcp
  sudo firewall-cmd --zone=libvirt --add-port=22623/tcp
  sudo firewall-cmd --zone=libvirt --add-port=443/tcp
  sudo firewall-cmd --zone=libvirt --add-port=80/tcp
}

function config_sshd() {
  echo "Harden SSH daemon"

  ### IBM Cloud machines by default allow SSH as root using the password. Given that the default one
  ### is extremely simple, we disable this option.

  sudo sed -i "s/.*RSAAuthentication.*/RSAAuthentication yes/g" /etc/ssh/sshd_config
  sudo sed -i "s/.*PubkeyAuthentication.*/PubkeyAuthentication yes/g" /etc/ssh/sshd_config
  sudo sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config

  sudo systemctl restart sshd.service
}

function additional_configs() {
    if [ "${ADD_USER_TO_SUDO}" != "n" ]; then
        current_user=$(whoami)
        echo "Make $current_user sudo passwordless"
        echo "$current_user ALL=(ALL:ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$current_user
    fi

    if sudo virsh net-list --all | grep default | grep inactive; then
        echo "default network is inactive, fixing it"
        if sudo ip link del virbr0-nic; then
            echo "Deleting virbr0-nic"
        fi
        if sudo ip link del virbr0; then
            echo "Deleting virbr0"
        fi
        sudo virsh net-start default
    fi
    touch ~/.gitconfig
    sudo chmod ugo+rx "$(dirname "$(pwd)")"
    echo "make selinux to only print warnings"
    sudo setenforce permissive || true

    if [ ! -f ~/.ssh/id_rsa ]; then
        ssh-keygen -t rsa -f ~/.ssh/id_rsa -P ''
    fi
    sudo chmod 600 ~/.ssh/id_rsa

    sudo firewall-cmd --zone=libvirt --add-port=59151-59154/tcp

    echo "enabling ipv6"
    sudo sed -ir 's/net.ipv6.conf.all.disable_ipv6[[:blank:]]*=[[:blank:]]*1/net.ipv6.conf.all.disable_ipv6 = 0/g' /etc/sysctl.conf
    sudo sed -i -e '/net.core.somaxconn/d' -e '$a net.core.somaxconn = 2000' /etc/sysctl.conf
    sudo sysctl --load

    echo "opening port 8500 for iPXE boot"
    sudo firewall-cmd --zone=libvirt --add-port=8500/tcp

    echo "opening port 7500 for Tang server"
    sudo firewall-cmd --zone=libvirt --add-port=7500/tcp
}

function config_dnf() {
    echo "Tune dnf configuration"
    local dnf_config_file="/etc/dnf/dnf.conf"

    if ! grep -q "fastestmirror" "${dnf_config_file}"; then
        echo "fastestmirror=1" | sudo tee --append "${dnf_config_file}"
    fi

    if ! grep -q "max_parallel_downloads" "${dnf_config_file}"; then
        echo "max_parallel_downloads=10" | sudo tee --append "${dnf_config_file}"
    fi
}

if [ $# -eq 0 ]; then
    config_dnf
    config_additional_modules
    install_packages
    install_libvirt
    install_runtime_container
    install_skipper
    config_firewalld
    config_squid
    fix_ipv6_routing
    config_chronyd
    config_nginx
    additional_configs
    install_virt_install
else
    $@
fi
