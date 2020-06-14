set -euo pipefail

export NO_EXTERNAL_PORT=${NO_EXTERNAL_PORT:-n}
export ADD_USER_TO_SUDO=${ADD_USER_TO_SUDO:-n}


function version_is_greater() {
    if [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; then
        return
    fi
    echo $(printf '%s\n' "$2" "$1" | sort -V | head -n1)
    false
}


function install_libvirt() {
  echo "Installing libvirt..."
  sudo dnf install -y libvirt libvirt-devel libvirt-daemon-kvm qemu-kvm
  sudo systemctl enable --now libvirtd

  current_version="$(libvirtd --version | awk '{print $3}')"
  minimum_version="5.5.100"

  echo "Setting libvirt values"
  sudo sed -i -e 's/#listen_tls/listen_tls/g' /etc/libvirt/libvirtd.conf
  sudo sed -i -e 's/#listen_tcp/listen_tcp/g' /etc/libvirt/libvirtd.conf
  sudo sed -i -e 's/#auth_tcp = "sasl"/auth_tcp = "none"/g' /etc/libvirt/libvirtd.conf
  sudo sed -i -e 's/#tcp_port/tcp_port/g' /etc/libvirt/libvirtd.conf
  sudo sed -i -e 's/#security_driver = "selinux"/security_driver = "none"/g' /etc/libvirt/qemu.conf

  if ! version_is_greater "$current_version" "$minimum_version"; then
    echo "Adding --listen flag to libvirt"
    sudo sed -i -e 's/#LIBVIRTD_ARGS="--listen"/LIBVIRTD_ARGS="--listen"/g' /etc/sysconfig/libvirtd
    sudo systemctl restart libvirtd
  else
    echo "libvirtd version is greater then 5.5.x, starting libvirtd-tcp.socket"
    sudo systemctl stop libvirtd
    sudo systemctl restart libvirtd.socket
    sudo systemctl enable --now libvirtd-tcp.socket
    sudo systemctl start libvirtd-tcp.socket
    sudo systemctl start libvirtd
  fi
  if sudo virsh net-list --all | grep default | grep  inactive; then
      echo "default network is inactive, fixing it"
      sudo ip link del virbr0-nic
      sudo ip link del virbr0
      sudo virsh net-start default
  fi
  current_user=$(whoami)
  echo "Adding user $current_user ti libvirt and qemu groups"
  sudo gpasswd -a $current_user libvirt
  sudo gpasswd -a $current_user qemu

}

function install_runtime_container() {
  echo "Installing container runitme package"
  if ! [ -x "$(command -v docker)" ] && ! [ -x "$(command -v podman)" ]; then
    sudo dnf install podman -y
  elif [ -x "$(command -v podman)" ]; then
    current_version="$(podman -v | awk '{print $3}')"
    minimum_version="1.6.4"
    if ! version_is_greater "$current_version" "$minimum_version"; then
      sudo dnf install podman-$minimum_version  -y
    fi
  else
    echo "docker or podman is already installed"
  fi
}

function install_packages(){
  echo "Installing dnf packages"
  sudo dnf install -y make python3 python3-pip git jq bash-completion xinetd
  sudo systemctl enable --now xinetd
}

function install_skipper() {
   echo "Installing skipper and adding ~/.local/bin to PATH"
   pip3 install strato-skipper==1.22.0 --user
   sudo cp ~/.local/bin/skipper /usr/local/bin
   # TODO maybe better to add ,local to PATH
   # grep -qxF "export PATH=~/.local/bin:$PATH" ~/.bashrc || echo "export PATH=~/.local/bin:$PATH" >> ~/.bashrc
   # export PATH="$PATH:~/.local/bin"
}

function config_firewalld() {
  echo "Config firewall"
  sudo systemctl start firewalld
  if  [ "${NO_EXTERNAL_PORT}" = "n" ];then
    echo "configuring external ports"
    sudo firewall-cmd --zone=public --add-port=6000/tcp
    sudo firewall-cmd --zone=public --add-port=6008/tcp
  fi
  echo "configuring libvirt zone ports ports"
  sudo firewall-cmd --zone=libvirt --add-port=6000/tcp
  sudo firewall-cmd --zone=libvirt --add-port=6008/tcp
  # sudo firewall-cmd --reload
  echo "Restarting libvirt after firewalld changes"
  sudo systemctl restart libvirtd
}

function additional_configs() {
  if  [ "${ADD_USER_TO_SUDO}" != "n" ];then
    current_user=$(whoami)
    echo "Make $current_user sudo passwordless"
    echo "$current_user ALL=(ALL:ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$current_user
  fi

  if sudo virsh net-list --all | grep default | grep  inactive; then
    echo "default network is inactive, fixing it"
    sudo ip link del virbr0-nic
    sudo ip link del virbr0
    sudo virsh net-start default
  fi
  touch ~/.gitconfig
  sudo chmod ugo+rx "$(dirname "$(pwd)")"
  sudo setenforce 0
}


install_packages
install_libvirt
install_runtime_container
install_skipper
config_firewalld
additional_configs
