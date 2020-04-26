
function install_minikube() {
  if ! [ -x "$(command -v minikube)" ]; then
  echo "Installing minikube..."
  curl -Lo minikube https://storage.googleapis.com/minikube/releases/v1.8.2/minikube-linux-amd64
  chmod +x minikube
  cp minikube /usr/bin/
else
  echo "minikube is already installed"
fi
}

function install_kubectl() {
  if ! [ -x "$(command -v kubectl)" ]; then
  echo "Installing kubectl..."
  curl -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/v1.17.0/bin/linux/amd64/kubectl
  chmod +x kubectl
  mv kubectl /usr/bin/
else
  echo "kubectl is already installed"
fi
}

function install_kvm2_driver() {
  if ! [ -x "$(command -v docker-machine-driver-kvm2)" ]; then
  echo "Installing kvm2_driver..."
  curl -LO https://storage.googleapis.com/minikube/releases/latest/docker-machine-driver-kvm2
  chmod +x docker-machine-driver-kvm2
  mv docker-machine-driver-kvm2 /usr/bin/
else
  echo "docker-machine-driver-kvm2 is already installed"
fi
}

function install_oc() {
  if ! [ -x "$(command -v oc)" ]; then
    echo "Installing oc..."
    curl -Lo oc.tar.gz https://mirror.openshift.com/pub/openshift-v4/clients/oc/${OPENSHIFT_VERSION:-4.4}/linux/oc.tar.gz && tar -C /usr/local/bin -xf oc.tar.gz && rm -f oc.tar.gz
  else
    echo "oc is already installed"
  fi
}

install_minikube
install_kubectl
install_kvm2_driver
install_oc
