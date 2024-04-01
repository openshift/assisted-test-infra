source "nutanix" "test-infra" {
  nutanix_username = var.nutanix_username
  nutanix_password = var.nutanix_password
  nutanix_endpoint = var.nutanix_endpoint
  nutanix_port     = var.nutanix_port
  nutanix_insecure = var.nutanix_insecure
  cluster_name     = var.nutanix_cluster
  os_type          = "Linux"
  user_data = base64encode(file("cloud-config.yaml"))

  # vm_disks {
  #  image_type = "ISO_IMAGE"
  #  source_image_name = var.centos_iso_image_name
  # }

  # cd_files = ["centos-config/ks.cfg"]
  # cd_label = "OEMDRV"

  vm_disks {
    image_type = "DISK_IMAGE"
    source_image_uri = "https://cloud.centos.org/centos/8-stream/x86_64/images/CentOS-Stream-GenericCloud-8-20230501.0.x86_64.qcow2"
    disk_size_gb = var.disk_size
  }

  vm_nics {
    subnet_name       = var.nutanix_subnet
  }

  # SSH
  ssh_username = "root"
  ssh_password = "packer"
  ssh_private_key_file = var.ssh_private_key_file

  # Hardware Configuration
  cpu = var.vcpus
  memory_mb = var.memory_size

  # Location Configuration
  image_name =  var.image_name
  force_deregister  = true

  # Shutdown Configuration
  shutdown_command = "shutdown -P now"
  shutdown_timeout = "2m"
}
