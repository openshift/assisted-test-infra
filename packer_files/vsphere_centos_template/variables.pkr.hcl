//////
// vSphere variables
//////

variable "vsphere_server" {
  type        = string
  description = "vSphere vcenter server ip address or fqdn (vCenter server name for vSphere API operations)"
}

variable "vsphere_username" {
  type        = string
  description = "vSphere vcenter server username"
}

variable "vsphere_password" {
  type        = string
  description = "vSphere vcenter server password"
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

variable "vsphere_folder" {
  type        = string
  description = "Create VSphere vm under this folder for easy management(For the CI). Folder name shouldn't end with a slash"
  default = ""
}

### Builder variables
variable "vm_name" {
  type = string
  default = "test"
  description = "The VM name - should be unique under this folder"
}

variable "disk_size" {
  type = number
  default = 240000
  description = "The VM disk size in MB. default 80G"
}

variable "memory_size" {
  type = string
  default = "16384"
  description = "The VM RAM size in MB. TODO: Adjust this variable to the right size"
}

variable "vcpus" {
  type = string
  default = "4"
  description = "The num of CPUs for this VM. TODO: Adjust this variable to the right size"
}

variable "iso_url" {
  type = string
  default = "https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/iso/CentOS-Stream-9-latest-x86_64-boot.iso"
  description = "The Centos8 ISO download URL"
}

variable "iso_checksum" {
  type = string
  description = "The Centos ISO checksum. See checksum at https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/iso/CentOS-Stream-9-latest-x86_64-boot.iso.SHA256SUM"
}

variable "root_password" {
  type = string
  default = "test"
  description = "The os root password"
}

variable "ssh_public_key" {
  type = string
  description = "The public ssh key, added as a ssh authorized key"
}

variable "ssh_private_key_file" {
  type = string
  description = "The private ssh key path, used to authenticate against the new template"
}

variable "ssh_bastion_host" {
  type = string
  default = ""
  description = "SSH bastion host. used for testing since we have no direct access to the vsphere environment"
}

variable "ssh_bastion_username" {
  type = string
  default = ""
  description = "SSH bastion username. used for testing since we have no direct access to the vsphere environment"
}

variable "ssh_bastion_private_key_file" {
  type = string
  default = ""
  description = "SSH bastion private key. used for testing since we have no direct access to the vsphere environment"
}
