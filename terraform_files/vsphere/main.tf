terraform {
  required_providers {
    vsphere = {
      source = "hashicorp/vsphere"
      version = "2.0.2"
    }
  }
}

locals {
  hasISO = var.iso_download_path != "" && var.iso_download_path != null
}

provider "vsphere" {
  user                 = var.vsphere_username
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_vcenter
  allow_unverified_ssl = true
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
  path          = var.cluster_name
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
  destination_file = "ISOs/${basename(var.iso_download_path)}"
}

# Creating the master VMs.
resource "vsphere_virtual_machine" "vm" {
  count = var.masters_count

  name                        = "${var.cluster_name}-master-${count.index}"
  resource_pool_id            = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id                = data.vsphere_datastore.datastore.id
  num_cpus                    = var.master_vcpu
  num_cores_per_socket        = var.vsphere_control_plane_cores_per_socket
  memory                      = var.master_memory
  guest_id                    = "coreos64Guest"
  folder                      = vsphere_folder.folder.path
  enable_disk_uuid            = "true"
  # no network before booting from the ISO file, which isn't available until prepare_for_installation stage
  wait_for_guest_net_routable = local.hasISO
  wait_for_guest_net_timeout  = local.hasISO ? 5 : 0

  network_interface {
    network_id = data.vsphere_network.network.id
  }

  disk {
    label            = "master-${count.index}-disk-0"
    size             = var.master_disk_size_gib
    eagerly_scrub    = false
    thin_provisioned = true
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

