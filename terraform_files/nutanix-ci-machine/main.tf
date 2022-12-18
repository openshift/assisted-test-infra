terraform {
  required_providers {
    nutanix = {
      source  = "nutanix/nutanix"
      version = "1.7.1"
    }
  }
}

provider "nutanix" {
  username     = var.nutanix_username
  password     = var.nutanix_password
  endpoint     = var.nutanix_endpoint
  port         = var.nutanix_port
  insecure     = true
  wait_timeout = 60
  session_auth = false
}

data "nutanix_cluster" "cluster" {
  name = var.nutanix_cluster
}

data "nutanix_subnet" "subnet" {
  subnet_name = var.nutanix_subnet
}

data "nutanix_image" "image" {
  image_name = var.iso_name
}

resource "nutanix_virtual_machine" "vm" {
  name                 = "assisted-ci-build-${var.build_id}"
  cluster_uuid         = data.nutanix_cluster.cluster.id
  num_vcpus_per_socket = var.cores_per_socket
  memory_size_mib      = var.memory
  num_sockets          = var.vcpu

  boot_device_order_list = ["DISK"]
  boot_type              = "LEGACY"

  enable_cpu_passthrough = true

  disk_list {
    data_source_reference = {
      kind = "image"
      uuid = data.nutanix_image.image.id
    }
  }

  nic_list {
    subnet_uuid = data.nutanix_subnet.subnet.id
  }
}
