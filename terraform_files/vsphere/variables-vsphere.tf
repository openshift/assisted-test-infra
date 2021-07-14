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

///////////
// Test infra variables
///////////


variable "cluster_name" {
  type = string
  description = <<EOF
AI cluster name
All the resources will be located under a folder with this name
and tagged with the cluster name
The resources should be associate with this name for easy recognition.
EOF
}

variable "iso_download_path" {
  type        = string
  description = "The ISO path (We have to upload this file to the vsphere)"
  default = ""
}

///////////
// Control Plane machine variables
///////////

variable "masters_count" {
  type = string
  default = "3"
  description = "The number of master nodes to be created."
}

variable "master_memory" {
  type = number
  default = 16984
  description = "The size of the master's virtual machine's memory, in MB"
}

variable "master_disk_size_gib" {
  type = number
  default = 120
  description = "The size of the master's disk, in GB"
}

variable "master_vcpu" {
  type = number
  default = 4
  description = "The total number of virtual processor cores to assign to the master virtual machine."
}

variable "vsphere_control_plane_cores_per_socket" {
  type = number
  default = 1
  description = <<EOF
The number of cores per socket(cpu) in this virtual machine.
The number of vCPUs on the virtual machine will be num_cpus divided by num_cores_per_socket.
If specified, the value supplied to num_cpus must be evenly divisible by this value. Default: 1
EOF
}