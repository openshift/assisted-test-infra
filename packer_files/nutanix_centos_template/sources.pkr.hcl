locals {
  ssh_public_key_content = file(var.ssh_public_key)
}

source "nutanix" "test-infra" {
  nutanix_username = var.nutanix_username
  nutanix_password = var.nutanix_password
  nutanix_endpoint = var.nutanix_endpoint
  nutanix_port     = var.nutanix_port
  nutanix_insecure = var.nutanix_insecure
  cluster_name     = var.nutanix_cluster
  os_type          = "Linux"
  user_data = base64encode(file("cloud-config.yaml"))

  vm_disks {
    image_type       =  "DISK_IMAGE"
    source_image_uri =  var.centos_disk_image_url
    disk_size_gb     =  var.disk_size / 1024
  }

  vm_nics {
    subnet_name = var.nutanix_subnet
  }

  # SSH
  ssh_username = "root"
  ssh_password = var.root_password
  ssh_private_key_file = var.ssh_private_key_file

  # Hardware Configuration
  cpu = var.vcpus
  memory_mb = var.memory_size

  # Location Configuration
  image_name = var.image_name
  force_deregister = true

  # Shutdown Configuration
  shutdown_command = "shutdown -P now"
  shutdown_timeout = "2m"
}
