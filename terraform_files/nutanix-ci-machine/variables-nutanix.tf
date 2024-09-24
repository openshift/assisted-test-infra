//////
// Nutanix variables
//////

variable "nutanix_endpoint" {
  type        = string
  description = "Endpoint for the Prism Elements or Prism Central instance. This can also be specified with the NUTANIX_ENDPOINT environment variable"
}

variable "nutanix_username" {
  type        = string
  description = "Username for the Prism Elements or Prism Central instance. This can also be specified with the NUTANIX_USERNAME environment variable"
}

variable "nutanix_password" {
  type        = string
  description = "Password for the Prism Elements or Prism Central instance. This can also be specified with the NUTANIX_PASSWORD environment variable"
}

variable "nutanix_port" {
  type        = number
  description = "Port for the Prism Elements or Prism Central instance. This can also be specified with the NUTANIX_PORT environment variable. Defaults to 9440"
}

variable "nutanix_cluster" {
  type        = string
  description = "Nutanix cluster name"
}

variable "nutanix_subnet" {
  type        = string
  description = "Nutanix subnet name. While selected the nic Ip will be in that subnet addresses range"
}

variable "build_id" {
  type        = string
  description = "The CI build id"
}

variable "memory" {
  type        = number
  default     = 16384
  description = "RAM in MiB allocated to masters"
}

variable "vcpu" {
  type        = number
  default     = 4
  description = "The total number of virtual processor cores to assign to the virtual machine."
}

variable "disk_size" {
  type        = number
  default     = 650
  description = "The size of the virtual machine's disk, in GB"
}

variable "ssh_public_key" {
  type = string
  description = "The public ssh key, added as a ssh authorized key"
}

variable "ssh_private_key" {
  type = string
  description = "The private ssh key path, used to authenticate against the new template"
  sensitive   = true
}

variable "cloud_config_file" {
  type = string
  default = "cloud-config.yaml"
  description = "Name for the cloud init configuration"
}

variable "cloud_image_url" {
  type = string
  description = "Cloud image URL"
}

variable "cores_per_socket" {
  type        = number
  default     = 1
  description = <<EOF
The number of cores per socket(cpu) in this virtual machine.
The number of vCPUs on the virtual machine will be num_cpus divided by num_cores_per_socket.
If specified, the value supplied to num_cpus must be evenly divisible by this value. Default: 1
EOF
}
