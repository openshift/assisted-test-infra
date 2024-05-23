### Nutanix variables
variable "nutanix_username" {
  type = string
}

variable "nutanix_password" {
  type =  string
  sensitive = true
}

variable "nutanix_endpoint" {
  type = string
}

variable "nutanix_port" {
  type = number
}

variable "nutanix_insecure" {
  type = bool
  default = true
}

variable "nutanix_subnet" {
  type = string
}

variable "nutanix_cluster" {
  type = string
}

### Builder variables

variable "centos_iso_image_name" {
  type = string
}

variable "image_name" {
  type = string
  default = "test"
  description = "Image name"
}

variable "disk_size" {
  type = number
  default = 102400
  description = "The VM disk size in MB. default 100G"
}

variable "memory_size" {
  type = string
  default = "16384"
  description = "The VM RAM size in MB"
}

variable "vcpus" {
  type = string
  default = "4"
  description = "The num of CPUs for this VM. TODO: Adjust this variable to the right size"
}

variable "root_password" {
  type = string
  default = "packer"
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
