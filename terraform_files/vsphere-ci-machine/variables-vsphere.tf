//////
// vSphere variables
//////

variable "vsphere_vcenter" {
  type        = string
  description = "vSphere vcenter server ip address or fqdn (vCenter server name for vSphere API operations)"
}

variable "vsphere_username" {
  type        = string
  description = "vSphere vcenter server username"
}

variable "vsphere_password" {
  type        = string
  description = "vSphere vcenter server username"
}

variable "vsphere_cluster" {
  type        = string
  description = "vSphere cluster name, vsphere cluster is a cluster of hosts that it manages"
}

variable "vsphere_datacenter" {
  type        = string
  description = "vSphere data center name"
}

variable "vsphere_datastore" {
  type        = string
  description = "vSphere data store name"
}

variable "vsphere_network" {
  type        = string
  description = "vSphere publicly accessible network for cluster ingress and access. e.g VM Network"
}

variable template_name {
  type = string
  description = "The Fedora/Centos template name to clone, should exist on the vsphere"
}

///////////
// Creating a vsphere machine to deploy test-infra on it.
///////////

variable "build_id" {
  type        = string
  description = "The CI build id"
}

variable "vcpu" {
  type = number
  default = 4
  description = "The total number of virtual processor cores to assign to the virtual machine."
}

variable "memory" {
  type = number
  default = 16984
  description = "The size of the virtual machine's memory, in MB"
}

variable "disk_size" {
  type = number
  default = 120
  description = "The size of the virtual machine's disk, in GB"
}

variable "guest_id" {
  type = string
  description = "The server os type. see: https://code.vmware.com/apis/358/doc/vim.vm.GuestOsDescriptor.GuestOsIdentifier.html"
  default = "centos8_64Guest"
}

variable "domain" {
  type = string
  description = "The host domain name"
  default = "redhat.com"
}
