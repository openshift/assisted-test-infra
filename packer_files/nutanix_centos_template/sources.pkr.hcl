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

  vm_disks {
    image_type        = "ISO_IMAGE"
    source_image_name = var.centos_iso_image_name
  }

  cd_label = "OEMDRV"
  cd_content = {
    "ks.cfg" = templatefile("centos-config/ks.cfg", {
      ssh_public_key_content = local.ssh_public_key_content
      root_password  = var.root_password
    })
  }

  vm_disks {
    image_type   = "DISK"
    disk_size_gb = var.disk_size / 1024
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
