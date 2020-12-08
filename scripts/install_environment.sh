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
    echo "Installing libvirt..."
    sudo dnf install -y libvirt libvirt-devel libvirt-daemon-kvm qemu-kvm
    sudo systemctl enable libvirtd

    current_version="$(libvirtd --version | awk '{print $3}')"
    minimum_version="5.6.0"

    echo "Setting libvirt values"
    sudo sed -i -e 's/#listen_tls/listen_tls/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#listen_tcp/listen_tcp/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#auth_tcp = "sasl"/auth_tcp = "none"/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#tcp_port/tcp_port/g' /etc/libvirt/libvirtd.conf
    sudo sed -i -e 's/#security_driver = "selinux"/security_driver = "none"/g' /etc/libvirt/qemu.conf

    if ! version_is_greater "$current_version" "$minimum_version"; then
        echo "Minimal supported version of libvirt is $minimum_version"
        exit 1
    else
        if ! rpm -qa | grep libgcrypt-1.8.5-4; then
            mkdir -p build
            curl -Lo build/libgcrypt-1.8.5-4.el8.x86_64.rpm https://rpmfind.net/linux/centos/8.3.2011/BaseOS/x86_64/os/Packages/libgcrypt-1.8.5-4.el8.x86_64.rpm && sudo dnf -y install build/libgcrypt-1.8.5-4.el8.x86_64.rpm
        fi
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
}

function install_skipper() {
    echo "Installing skipper and adding ~/.local/bin to PATH"
    pip3 install strato-skipper==1.26.0 --user

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
    sudo sed -i  -e '/^.*allowed_ips.*$/d' -e '/^acl CONNECT.*/a acl allowed_ips src 2001:db8::/120' -e '/^http_access deny all/i http_access allow allowed_ips'  /etc/squid/squid.conf
    sudo systemctl restart squid
    sudo firewall-cmd --zone=libvirt --add-port=3128/tcp
}

function fix_ipv6_routing() {
  sudo sed -i '/^net[.]ipv6[.]conf[.][^.]*[.]accept_ra = 2$/d' /etc/sysctl.conf
  for intf in `ls -l /sys/class/net/ | grep root | grep -v virtual | awk '{print $9}'` ; do
      if sudo test ! -f "/proc/sys/net/ipv6/conf/${intf}/accept_ra"; then
          echo "WARNING: It looks like IPv6 is disabled on this host and might not work"
          return
      fi
      echo "net.ipv6.conf.${intf}.accept_ra = 2" | sudo tee --append /etc/sysctl.conf
  done
  sudo sysctl --load
  fname=/etc/NetworkManager/dispatcher.d/40-sysctl-load.sh
  sudo cat <<EOF > $fname
#! /bin/bash
sysctl --load
EOF
  sudo chmod +x $fname
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
    echo "disabling selinux by setenforce 0"
    sudo setenforce 0 || true
    sudo chmod 600 ssh_key/key
    sudo firewall-cmd --zone=libvirt --add-port=59151-59154/tcp
}

install_packages
install_libvirt
install_runtime_container
install_skipper
config_firewalld
config_squid
fix_ipv6_routing
additional_configs
