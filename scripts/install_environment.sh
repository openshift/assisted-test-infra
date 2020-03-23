
function install_libvirt() {
  if ! [ -x "$(command -v virsh)" ]; then
  echo "Installing libvirt..."
  yum install -y libvirt libvirt-devel libvirt-daemon-kvm qemu-kvm
	sed -i -e 's/#LIBVIRTD_ARGS="--listen"/LIBVIRTD_ARGS="--listen"/g' /etc/sysconfig/libvirtd
  sed -i -e 's/#listen_tls/listen_tls/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#listen_tcp/listen_tcp/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#auth_tcp = "sasl"/auth_tcp = "none"/g' /etc/libvirt/libvirtd.conf
  sed -i -e 's/#tcp_port/tcp_port/g' /etc/libvirt/libvirtd.conf
	systemctl enable --now libvirtd
else
  echo "libvirt is already installed"
fi
}

function install_runtime_container() {
  if ! [ -x "$(command -v docker)" ] || [ -x "$(command -v podman)" ]; then
  dnf config-manager --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
	dnf install docker-ce --nobest -y
	systemctl enable --now docker
else
  echo "docker or podman is already installed"
fi
}

function install_skipper() {
   yum install -y python3
   pip3 install strato-skipper
}

install_libvirt
install_runtime_container
install_skipper