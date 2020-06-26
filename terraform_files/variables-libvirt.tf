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

variable "machine_cidr" {
  type        = string
  description = "Cluster domain"
}

variable "libvirt_uri" {
  type        = string
  description = "libvirt connection URI"
}

variable "libvirt_network_if" {
  type        = string
  description = "The name of the bridge to use"
}

variable "libvirt_network_name" {
  type        = string
  description = "The name of the network to use"
}

//variable "os_image" {
//  type        = string
//  description = "The URL of the OS disk image"
//}

//variable "discovery_ip" {
//  type        = string
//  description = "Ip of discovery server"
//}

variable "libvirt_master_ips" {
  type        = list(string)
  description = "the list of desired master ips. Must match master_count"
}

variable "libvirt_worker_ips" {
  type        = list(string)
  description = "the list of desired worker ips. Must match master_count"
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
