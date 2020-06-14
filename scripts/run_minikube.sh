
function configure_minikube() {
  echo "Configuring minikube..."
  minikube config set ShowBootstrapperDeprecationNotification false
  minikube config set WantUpdateNotification false
  minikube config set WantReportErrorPrompt false
  minikube config set WantKubectlDownloadMsg false
}

function init_minikube() {
    #If the vm exists, it has already been initialized
    if [[ "$(virsh -c qemu:///system list --all)" != *"minikube"* ]]; then
      #minikube start --kvm-network=test-infra-net --vm-driver=kvm2 --memory=4096 --force
	    minikube start --vm-driver=kvm2 --memory=4096 --force
    fi
}

configure_minikube
init_minikube
