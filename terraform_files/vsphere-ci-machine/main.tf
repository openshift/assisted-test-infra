terraform {
  required_providers {
    vsphere = {
      source = "hashicorp/vsphere"
      version = "2.0.2"
    }
  }
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

# Creating a folder, all the vms would be created into this folder.
resource "vsphere_folder" "folder" {
  path          = "assisted-test-infra-ci/build-${var.build_id}"
  type          = "vm"
  datacenter_id = data.vsphere_datacenter.datacenter.id
}

# The VSphere template to clone
data "vsphere_virtual_machine" template {
  name          = "/${data.vsphere_datacenter.datacenter.name}/vm/assisted-test-infra-ci/${var.template_name}"
  datacenter_id = data.vsphere_datacenter.datacenter.id
}

# Creating the master VMs.
resource "vsphere_virtual_machine" "vm" {
  name                        = "assisted-ci-build-${var.build_id}"
  resource_pool_id            = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id                = data.vsphere_datastore.datastore.id
  num_cpus                    = var.vcpu
  num_cores_per_socket        = 1
  memory                      = var.memory
  guest_id                    = var.guest_id
  folder                      = vsphere_folder.folder.path
  enable_disk_uuid            = "true"
  wait_for_guest_net_routable = true
  wait_for_guest_net_timeout  = 15
  firmware = data.vsphere_virtual_machine.template.firmware
  scsi_type = data.vsphere_virtual_machine.template.scsi_type

  network_interface {
    network_id = data.vsphere_network.network.id
  }

  disk {
    label            = "assisted-ci-0"
    size             = var.disk_size
    eagerly_scrub    = false
    thin_provisioned = true
  }

  clone {
    template_uuid = data.vsphere_virtual_machine.template.id

    customize {
      linux_options {
        host_name = "AI-CI-build-${var.build_id}"
        domain = var.domain
      }

      network_interface {}
    }
  }
}