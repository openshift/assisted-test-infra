
function install_libvirt() {
  if ! [ -x "$(command -v virsh)" ]; then
    echo "Installing libvirt..."
    dnf install -y libvirt libvirt-devel libvirt-daemon-kvm qemu-kvm
    systemctl enable --now libvirtd
    else
  echo "libvirt is already installed"
  fi
  sed -i -e 's/#LIBVIRTD_ARGS="--listen"/LIBVIRTD_ARGS="--listen"/g' /etc/sysconfig/libvirtd
  sed -i -e 's/#listen_tls/listen_tls/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#listen_tcp/listen_tcp/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#auth_tcp = "sasl"/auth_tcp = "none"/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#tcp_port/tcp_port/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#security_driver = "selinux"/security_driver = "none"/g' /etc/libvirt/qemu.conf


}

function install_runtime_container() {
  if ! [ -x "$(command -v docker)" ] && ! [ -x "$(command -v podman)" ]; then
  dnf config-manager --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
	dnf install docker-ce --nobest -y
	systemctl enable --now docker
elif [ -x "$(command -v podman)" ]; then
  dnf install podman -y
else
  echo "docker or podman is already installed"
fi
}

function install_packages(){
  dnf install -y make python3 git jq bash-completion
}

function install_skipper() {
   pip3 install strato-skipper==1.20.0
}

install_packages
install_libvirt
install_runtime_container
install_skipper
systemctl restart libvirtd
touch ~/.gitconfig
#setfacl -R -m u:qemu:rwx storage_pool
chmod ugo+rx "$(dirname "$(pwd)")"