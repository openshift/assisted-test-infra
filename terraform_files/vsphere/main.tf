terraform {
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "=2.5.1"
    }
  }
}

locals {
  hasISO = var.iso_download_path != "" && var.iso_download_path != null
  folder = var.vsphere_folder != "" ? var.vsphere_folder : var.cluster_name
}

provider "vsphere" {
  user                 = var.vsphere_username
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_server
  allow_unverified_ssl = true
  client_debug         = true
  client_debug_path    = "/tmp/govnomi"
}

data "vsphere_datacenter" "datacenter" {
  name = var.vsphere_datacenter
}

data "vsphere_compute_cluster" "cluster" {
  name          = var.vsphere_cluster
  datacenter_id = data.vsphere_datacenter.datacenter.id
}

data "vsphere_datastore" "datastore" {
  name          = var.vsphere_datastore
  datacenter_id = data.vsphere_datacenter.datacenter.id
}

data "vsphere_network" "network" {
  name          = var.vsphere_network
  datacenter_id = data.vsphere_datacenter.datacenter.id
}

# Tagging every VirtualMachine, ResourcePool, Folder with the cluster name to easy recognition and add the description:
# "Created by the test-infra, do not delete manually"
resource "vsphere_tag_category" "category" {
  name        = var.cluster_name
  description = "Created by the test-infra, do not delete manually"
  cardinality = "SINGLE"

  associable_types = [
    "VirtualMachine",
    "ResourcePool",
    "Folder"
  ]
}

resource "vsphere_tag" "tag" {
  name        = var.cluster_name
  category_id = vsphere_tag_category.category.id
  description = "Created by the test-infra, do not delete manually"
}

# Creating a folder, all the vms would be created into this folder.
resource "vsphere_folder" "folder" {
  # don't try to create a pre-existing folder
  count         = var.vsphere_folder != "" ? 0 : 1
  path          = "${var.vsphere_parent_folder}/${var.cluster_name}"
  type          = "vm"
  datacenter_id = data.vsphere_datacenter.datacenter.id
  tags          = [vsphere_tag.tag.id]
}

# Uploading the ISO file.
resource "vsphere_file" "ISO_UPLOAD" {
  # upload the file only if exist
  count            = local.hasISO ? 1 : 0
  datacenter       = var.vsphere_datacenter
  datastore        = var.vsphere_datastore
  source_file      = var.iso_download_path
  destination_file = "test/cluster-${var.cluster_name}/${basename(var.iso_download_path)}"
}

# Creating the master VMs.
resource "vsphere_virtual_machine" "master" {
  count = var.masters_count

  name                 = "${var.cluster_name}-master-${count.index}"
  resource_pool_id     = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id         = data.vsphere_datastore.datastore.id
  num_cpus             = var.master_vcpu
  num_cores_per_socket = var.vsphere_control_plane_cores_per_socket
  memory               = var.master_memory
  guest_id             = "coreos64Guest"
  folder               = var.vsphere_folder != "" ? "${var.vsphere_parent_folder}/${local.folder}" : vsphere_folder.folder[0].path
  enable_disk_uuid     = "true"
  hardware_version     = 15
  # no network before booting from the ISO file, which isn't available until prepare_for_installation stage
  wait_for_guest_net_routable = local.hasISO
  wait_for_guest_net_timeout  = local.hasISO ? 5 : 0

  network_interface {
    network_id = data.vsphere_network.network.id
  }

  dynamic "disk" {
    for_each = range(var.master_disk_count)
    content {
      label            = "master-${count.index}-disk-${count.index + 1}-${disk.key}"
      size             = var.master_disk_size_gib
      eagerly_scrub    = false
      unit_number      = disk.key > 0 ? disk.key : 0
      thin_provisioned = true
    }
  }

  dynamic "cdrom" {
    # create the cdrom device only if the iso file is available
    for_each = local.hasISO ? [1] : []
    content {
      datastore_id = data.vsphere_datastore.datastore.id
      path         = local.hasISO ? vsphere_file.ISO_UPLOAD[0].destination_file : null
    }
  }

  tags = [vsphere_tag.tag.id]
}

# Creating the workers VMs.
resource "vsphere_virtual_machine" "worker" {
  count = var.workers_count

  name                 = "${var.cluster_name}-worker-${count.index}"
  resource_pool_id     = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id         = data.vsphere_datastore.datastore.id
  num_cpus             = var.worker_vcpu
  num_cores_per_socket = var.vsphere_control_plane_cores_per_socket
  memory               = var.worker_memory
  guest_id             = "coreos64Guest"
  folder               = var.vsphere_folder != "" ? "${var.vsphere_parent_folder}/${local.folder}" : vsphere_folder.folder[0].path
  enable_disk_uuid     = "true"
  hardware_version     = 15
  # no network before booting from the ISO file, which isn't available until prepare_for_installation stage
  wait_for_guest_net_routable = local.hasISO
  wait_for_guest_net_timeout  = local.hasISO ? 5 : 0

  network_interface {
    network_id = data.vsphere_network.network.id
  }


  dynamic "disk" {
    for_each = range(var.worker_disk_count)
    content {
      label            = "worker-${count.index}-disk-${count.index + 1}-${disk.key}"
      size             = var.worker_disk_size_gib
      eagerly_scrub    = false
      unit_number      = disk.key > 0 ? disk.key : 0
      thin_provisioned = true
    }
  }

  dynamic "cdrom" {
    # create the cdrom device only if the iso file is available
    for_each = local.hasISO ? [1] : []
    content {
      datastore_id = data.vsphere_datastore.datastore.id
      path         = local.hasISO ? vsphere_file.ISO_UPLOAD[0].destination_file : null
    }
  }

  tags = [vsphere_tag.tag.id]
}
