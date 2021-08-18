source "vsphere-iso" "test-infra-template" {
  vcenter_server =  var.vsphere_vcenter
  username =  var.vsphere_username
  password =  var.vsphere_password
  datacenter =  var.vsphere_datacenter
  insecure_connection =  true
  ssh_username = "root"
  ssh_password = var.root_password
  convert_to_template =  true

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
    "centos8-ks.cfg" = templatefile("centos-config/centos8-ks.cfg", { password = var.root_password })
  }

  cd_label = "ksdata"
  remove_cdrom = true
  ip_wait_timeout = "1h"

  boot_command = [
    "<tab><wait>",
    " ks=linux ks=cdrom:/centos8-ks.cfg<enter>"
  ]

  network_adapters {
    network = "VM Network"
    network_card = "vmxnet3"
  }

  storage {
    disk_size = var.disk_size
    disk_thin_provisioned = true
    disk_eagerly_scrub = false
  }
}