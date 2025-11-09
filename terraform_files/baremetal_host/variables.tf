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

variable "networks" {
  type = list(object({
    name     = string,
    hostname = optional(string),
    ips      = list(string),
    mac      = string
  }))
  description = "Network devices configuration for the host."
  default     = []
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
  description = "Disk space in bytes allocated to the host."
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

variable "boot_devices" {
  type        = list(string)
  description = "the list of boot devices in the desired order of boot"
  default     = ["hd", "cdrom"]
}

variable "uefi_boot_firmware" {
  description = "The uefi boot firmware path in hypervisor"
  type        = string
  default     = ""
}

variable "uefi_boot_template" {
  description = "The uefi boot template path in hypervisor"
  type        = string
  default     = ""
}

