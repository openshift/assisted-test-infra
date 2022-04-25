#!/bin/bash
set -euo pipefail

export EXTERNAL_PORT=${EXTERNAL_PORT:-y}
export ADD_USER_TO_SUDO=${ADD_USER_TO_SUDO:-n}

function version_is_greater() {
    if [ "$(head -n1 <(printf '%s\n' "$2" "$1" | sort -V))" = "$2" ]; then
        return
    fi
    echo "$(head -n1 <(printf '%s\n' "$2" "$1" | sort -V))"
    false
}

function install_libvirt() {
    source /etc/os-release  # This should set `PRETTY_NAME` as environment variable

    # RHEL and CentOS require epel-release for swtpm and swtpm-tools packages
    case "${PRETTY_NAME}" in
    "Red Hat Enterprise Linux 8"* | "CentOS Linux 8"* | "Rocky Linux 8"*)
        sudo dnf install -y \
            https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
        ;;
    "Red Hat Enterprise Linux 7"* | "CentOS Linux 7"*)
        sudo dnf install -y \
            https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
        ;;
    esac

    # The package selinux-policy should be installed first because otherwise, RPMs install will fail due to a lack of SELinux config.
    # Some RPMs have SELinux plugins that will search for /etc/selinux/targeted/contexts/files/file_contexts
    # See https://access.redhat.com/solutions/6062341
    echo "Install selinux-policy RPM"
    sudo dnf install -y selinux-policy

    # TODO: support libvirt >= 6.0.0-37-1
    SPECIFIC_LIBVIRT_VERSION=""
    if [[ "${PRETTY_NAME}" == "Rocky Linux 8"* ]]; then
        echo "Installing a downgraded version of libvirt, as we currently don't support the newer one..."
        SPECIFIC_LIBVIRT_VERSION="-6.0.0-37.module+el8.5.0+670+c4aa478c"
    fi

    echo "Installing libvirt..."
    sudo dnf install -y \
        libvirt${SPECIFIC_LIBVIRT_VERSION} \
        libvirt-devel${SPECIFIC_LIBVIRT_VERSION} \
        libvirt-daemon-kvm${SPECIFIC_LIBVIRT_VERSION} \
        qemu-kvm \
        libgcrypt \
        swtpm \
        swtpm-tools

    sudo systemctl enable libvirtd

    current_version="$(libvirtd --version | awk '{print $3}')"
    minimum_version="5.5.100"

    echo "Setting libvirt values"
    sudo sed -i -e 's/#listen_tls/listen_tls/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#listen_tcp/listen_tcp/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#auth_tcp = "sasl"/auth_tcp = "none"/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#tcp_port/tcp_port/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#security_driver = "selinux"/security_driver = "none"/g' /etc/libvirt/qemu.conf

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
    sudo sed -i -e 's/LIBVIRTD_ARGS="--listen"/#LIBVIRTD_ARGS="--listen"/g' /etc/sysconfig/libvirtd
    sudo systemctl stop libvirtd
    sudo systemctl unmask libvirtd-tcp.socket
    sudo systemctl unmask libvirtd.socket
    sudo systemctl unmask libvirtd-ro.socket
    sudo systemctl restart libvirtd.socket
    sudo systemctl enable --now libvirtd-tcp.socket
    sudo systemctl start libvirtd-tcp.socket
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

function install_runtime_container() {
    echo "Installing container runtime package"
    if ! [ -x "$(command -v docker)" ] && ! [ -x "$(command -v podman)" ]; then
        sudo dnf install podman -y
    elif [ -x "$(command -v podman)" ]; then
        current_version="$(head -n1 <(podman version) | awk '{print $2}')"
        minimum_version="1.6.4"
        if ! version_is_greater "$current_version" "$minimum_version"; then
            sudo dnf install podman-$minimum_version -y
        fi
    else
        echo "docker or podman is already installed"
    fi

}

function install_packages() {
    echo "Installing dnf packages"
    sudo dnf install -y make python3 python3-pip git jq bash-completion xinetd
    sudo systemctl enable --now xinetd

    echo "Installing python packages"
    sudo pip3 install aicli

}

function install_skipper() {
    echo "Installing skipper and adding ~/.local/bin to PATH"
    pip3 install strato-skipper==1.29.2 --user

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
    sudo sed -i  -e '/^.*allowed_ips.*$/d' -e '/^acl CONNECT.*/a acl allowed_ips src 1001:db8::/120' -e '/^acl CONNECT.*/a acl allowed_ips src 1001:db8:0:200::/120' -e '/^http_access deny all/i http_access allow allowed_ips'  /etc/squid/squid.conf
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
  podman rm -f load_balancer || /bin/true
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
    IPXE_BOOT=${IPXE_BOOT:-false}
    if [ ${IPXE_BOOT} = "true" ]; then
        echo "Opening port 8500 for iPXE boot."
        sudo firewall-cmd --zone=libvirt --add-port=8500/tcp
    fi
}

if [ $# -eq 0 ]; then
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
else
    $@
fi
