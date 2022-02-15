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
  default = 80000
  description = "The VM disk size in MB. default 80G"
}

variable "memory_size" {
  type = string
  default = "16984"
  description = "The VM RAM size in MB. TODO: Adjust this variable to the right size"
}

variable "vcpus" {
  type = string
  default = "4"
  description = "The num of CPUs for this VM. TODO: Adjust this variable to the right size"
}

variable "iso_url" {
  type = string
  default = "https://vault.centos.org/8.5.2111/isos/x86_64/CentOS-8.5.2111-x86_64-boot.iso"
  description = "The Centos8 ISO download URL"
}

variable "iso_checksum" {
  type = string
  default = "9602c69c52d93f51295c0199af395ca0edbe35e36506e32b8e749ce6c8f5b60a"
  description = "The Centos8 ISO checksum"
}

variable "root_password" {
  type = string
  default = "test"
  description = "The os root password"
}

variable "ssh_public_key" {
  type = string
  default = ""
  description = "The public ssh key, added as a ssh authorized key"
}

variable "ssh_private_key_file" {
  type = string
  default = ""
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
