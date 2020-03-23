variable "cluster_id" {
  type        = string
  description = "The identifier for the cluster."
}

variable "master_count" {
  type        = number
  description = "The identifier for the cluster."
}

//variable "bootstrap_dns" {
//  default     = true
//  description = "Whether to include DNS entries for the bootstrap node or not."
//}

//variable "ignition_master" {
//  type        = string
//  description = "Servers ignition"
//}

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

variable "image_path" {
  type        = string
  description = "image type"
}