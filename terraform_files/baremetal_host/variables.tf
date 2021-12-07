variable "name" {
  type        = string
  description = "Identifying name for the host."
}

variable "memory" {
  type        = number
  description = "RAM in MiB allocated to the host."
}

variable "vcpu" {
  type        = number
  description = "Number of virtual cores allocated to the host."
}

variable "running" {
  type        = bool
  description = "Whether or not letting the host start running right away after its creation."
}

variable "image_path" {
  type        = string
  description = "Live CD image that should be booted from if hard disk is not bootable."
}

variable "cpu_mode" {
  type        = string
  description = "How CPU model of the libvirt guest should be configured."
  default     = "host-passthrough"
}

variable "cluster_domain" {
  type        = string
  description = "The domain for the cluster that all DNS records must belong."
}

variable "primary_network" {
  type        = string
  description = "Name of the libvirt network that should act as the node's primary network."
  default     = ""
}

variable "primary_ips" {
  type        = list(string)
  description = "IP addresses to assign to the host in the primary network."
  default     = []
}

variable "primary_mac" {
  type        = string
  description = "MAC address to assign to the host in the primary network."
  default     = ""
}

variable "secondary_network" {
  type        = string
  description = "Name of the libvirt network that should act as the node's secondary network."
  default     = ""
}

variable "secondary_ips" {
  type        = list(string)
  description = "IP addresses to assign to the host in the secondary network."
  default     = []
}

variable "secondary_mac" {
  type        = string
  description = "MAC address to assign to the host in the secondary network."
  default     = ""
}

variable "pool" {
  type        = string
  description = "Pool name to be used."
}

variable "disk_base_name" {
  type        = string
  description = "Prefix name to be used for namespacing disks."
}

variable "disk_size" {
  type        = number
  description = "Disk space in MiB allocated to the host."
}

variable "disk_count" {
  type        = number
  description = "Number of disks to attach to the host."
  default     = 1
}

variable "vtpm2" {
  type        = bool
  description = "Whether of not to emulate TPM v2 device on the host."
  default     = false
}
