
# Creating the master VMs.
resource "nutanix_virtual_machine" "master" {
  count                       = var.masters_count
  name                        = "${var.cluster_name}-master-${count.index}"
  cluster_uuid                = data.nutanix_cluster.cluster.id
  num_vcpus_per_socket        = var.nutanix_control_plane_cores_per_socket
  memory_size_mib             = var.master_memory
  num_sockets                 = var.master_vcpu

  boot_device_order_list      = ["CDROM", "DISK", "NETWORK"]
  boot_type                   = "LEGACY"

  disk_list {
    data_source_reference = {
      kind = "image"
      uuid = nutanix_image.image.id
    }
    device_properties {
      device_type = "CDROM"
    }
  }

    disk_list {
    disk_size_bytes = var.master_disk_size_gib * 1024 * 1024 * 1024
    device_properties {
      device_type = "DISK"
      disk_address = {
        device_index = 0
        adapter_type = "SATA"
      }

    }
  }

  nic_list {
    subnet_uuid = data.nutanix_subnet.subnet.id
  }
}

# Creating the worker VMs.
resource "nutanix_virtual_machine" "worker" {
  count                       = var.workers_count
  name                        = "${var.cluster_name}-worker-${count.index}"
  cluster_uuid                = data.nutanix_cluster.cluster.id
  num_vcpus_per_socket        = var.nutanix_control_plane_cores_per_socket
  memory_size_mib             = var.worker_memory
  num_sockets                 = var.worker_vcpu

  boot_device_order_list      = ["CDROM", "DISK", "NETWORK"]
  boot_type                   = "LEGACY"

  disk_list {
    data_source_reference = {
      kind = "image"
      uuid = nutanix_image.image.id
    }
    device_properties {
      device_type = "CDROM"
    }
  }

    disk_list {
    disk_size_bytes = var.worker_disk_size_gib * 1024 * 1024 * 1024
    device_properties {
      device_type = "DISK"
      disk_address = {
        device_index = 0
        adapter_type = "SATA"
      }
    }
  }

  nic_list {
    subnet_uuid = data.nutanix_subnet.subnet.id
  }
}
