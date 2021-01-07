variable "cluster_name" {
  type        = string
  description = "The identifier for the cluster."
}

variable "master_count" {
  type        = number
  description = "The identifier for the cluster."
}

variable "worker_count" {
  type        = number
  description = "Number of workers."
}

variable "cluster_domain" {
  type        = string
  description = "Cluster domain"
}

variable "machine_cidr_addresses" {
    type = list(string)
    description = "Addresses for machine CIDR network"
}

variable "provisioning_cidr_addresses" {
    type = list(string)
    description = "Addresses for provisioning CIDR network"
}

variable "libvirt_uri" {
  type        = string
  description = "libvirt connection URI"
}

variable "libvirt_network_if" {
  type        = string
  description = "The name of the bridge to use"
}

variable "libvirt_secondary_network_if" {
  type        = string
  description = "The name of the second bridge to use"
}

variable "libvirt_network_name" {
  type        = string
  description = "The name of the network to use"
}

variable "libvirt_secondary_network_name" {
  type        = string
  description = "The name of the second network to use"
}

variable "libvirt_network_mtu" {
  type        = number
  description = "The MTU of the network to use"
}

variable "libvirt_master_ips" {
  type        = list(list(string))
  description = "the list of desired master ips. Must match master_count"
}

variable "libvirt_secondary_master_ips" {
  type        = list(list(string))
  description = "the list of desired master second interface ips. Must match master_count"
}

variable "libvirt_master_macs" {
  type        = list(string)
  description = "the list of the desired macs for master interface"
}

variable "libvirt_secondary_master_macs" {
  type        = list(string)
  description = "the list of the desired macs for secondary master interface"
}

variable "libvirt_worker_ips" {
  type        = list(list(string))
  description = "the list of desired worker ips. Must match master_count"
}

variable "libvirt_secondary_worker_ips" {
  type        = list(list(string))
  description = "the list of desired worker second interface ips. Must match master_count"
}

variable "libvirt_worker_macs" {
  type        = list(string)
  description = "the list of the desired macs for worker interface"
}

variable "libvirt_secondary_worker_macs" {
  type        = list(string)
  description = "the list of the desired macs for secondary worker interface"
}

variable "api_vip" {
  type        = string
  description = "the API virtual IP"
}

# It's definitely recommended to bump this if you can.
variable "libvirt_master_memory" {
  type        = string
  description = "RAM in MiB allocated to masters"
  default     = "6144"
}

# At some point this one is likely to default to the number
# of physical cores you have.  See also
# https://pagure.io/standard-test-roles/pull-request/223
variable "libvirt_master_vcpu" {
  type        = string
  description = "CPUs allocated to masters"
  default     = "4"
}

variable "libvirt_worker_vcpu" {
  type        = string
  description = "CPUs allocated to workers"
  default     = "2"
}

variable "libvirt_worker_memory" {
  type        = string
  description = "RAM in MiB allocated to worker"
  default     = "4096"
}


variable "image_path" {
  type        = string
  description = "image type"
}

variable "libvirt_storage_pool_path" {
  type        = string
  description = "storage pool path"
}


variable "libvirt_worker_disk" {
  type        = string
  description = "Disk size in bytes allocated to worker"
  default     = "21474836480"
}

variable "libvirt_master_disk" {
  type        = string
  description = "Disk size in bytes allocated to master"
  default     = "21474836480"
}

variable "running" {
  type        = bool
  description = "Power on vms or not"
  default     = true
}

variable "cluster_inventory_id" {
  type      = string
}

variable "bootstrap_in_place" {
  type    = bool
  default = false
}

variable "static_macs" {
  description = "If true, static macs are configured for the network interfaces"
  type        = bool
}
