source "vsphere-iso" "test-infra-template" {
  vcenter_server =  var.vsphere_vcenter
  username =  var.vsphere_username
  password =  var.vsphere_password
  datacenter =  var.vsphere_datacenter
  insecure_connection =  true
  convert_to_template =  true

  # SSH
  ssh_username = "root"
  ssh_private_key_file = var.ssh_private_key_file
  ssh_bastion_host = var.ssh_bastion_host
  ssh_bastion_username = var.ssh_bastion_username
  ssh_bastion_private_key_file = var.ssh_bastion_private_key_file

  # Hardware Configuration
  CPUs = var.vcpus
  RAM = var.memory_size

  # Location Configuration
  vm_name =  var.vm_name
  folder =  var.vsphere_folder
  cluster =  var.vsphere_cluster
  datastore =  var.vsphere_datastore

  # Shutdown Configuration
  shutdown_command = "shutdown -P now"

  # ISO Configuration
  iso_checksum = var.iso_checksum
  iso_url = var.iso_url

  # Configuration
  guest_os_type =  "centos8_64Guest"
  notes =  "Built via Packer"

  cd_content = {
    "centos8-ks.cfg" = templatefile("centos-config/centos8-ks.cfg", { key = var.ssh_public_key, password = var.root_password })
  }

  cd_label = "ksdata"
  remove_cdrom = true
  ip_wait_timeout = "1h"

  boot_command = [
    "<tab><wait>",
    " inst.ks=linux inst.ks=cdrom:/centos8-ks.cfg<enter>"
  ]

  network_adapters {
    network = var.vsphere_network
    network_card = "vmxnet3"
  }

  storage {
    disk_size = var.disk_size
    disk_thin_provisioned = true
    disk_eagerly_scrub = false
  }
}