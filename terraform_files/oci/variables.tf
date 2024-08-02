variable "unique_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the resources names related to the current job"
  default     = "12345678901234567890"
}

variable "cluster_name" {
  type        = string
  description = <<EOF
Assisted installer cluster name
All the resources will be located under a folder with this name
and tagged with the cluster name
The resources should be associate with this name for easy recognition.
EOF
}

variable "iso_download_path" {
  type        = string
  description = "Path to the discovery ISO"
}

///////////
// OCI variables
///////////


variable "oci_tenancy_oicd" {
  type        = string
  description = "OCID of your tenancy"
}

variable "oci_user_oicd" {
  type        = string
  description = "OCID of the user calling the API"
}

variable "oci_key_fingerprint" {
  type        = string
  description = "Fingerprint for the key pair being used"
}

variable "oci_private_key_path" {
  type        = string
  description = "The path of the private key file"
}

variable "oci_region" {
  type        = string
  description = "An Oracle Cloud Infrastructure region"
}

variable "oci_compartment_oicd" {
  type        = string
  description = "Parent compartment where the resources will be created"
}

variable "base_dns_domain" {
  type        = string
  description = "DNS zone name where the records for the cluster will be created"
}

variable "oci_vcn_oicd" {
  type        = string
  description = "VCN ID where the cluster will be created"
}

variable "oci_private_subnet_oicd" {
  type        = string
  description = "Subnet ID of the private subnet"
}

variable "oci_public_subnet_oicd" {
  type        = string
  description = "Subnet ID of the public subnet"
}

variable "oci_iscsi_subnet_oicd" {
  type        = string
  description = "Subnet ID of the iscsi subnet"
}

variable "oci_extra_node_nsg_oicds" {
  type        = list(string)
  description = "Extra network security group IDs be assigned to cluster nodes (e.g.: to allow nodes to reach assisted service or allow SSH access to nodes)"
}

variable "oci_extra_lb_nsg_oicds" {
  type        = list(string)
  description = "Extra network security group IDs be assigned to load balancer (e.g.: to allow API/MCS/HTTP/HTTPS access to the cluster)"
}

variable "oci_boot_volume_type" {
  type        = string
  description = "Boot volume type to use for the cluster nodes"
  default     = null
}

variable "instance_shape" {
  type        = string
  description = "The shape of the instance. The shape determines the number of CPUs and the amount of memory allocated to the instance"
  default     = "VM.Standard3.Flex"
}

variable "instance_platform_config_type" {
  type        = string
  description = "The type of platform being configured. (Supported types=[INTEL_VM, AMD_MILAN_BM, AMD_ROME_BM, AMD_ROME_BM_GPU, INTEL_ICELAKE_BM, INTEL_SKYLAKE_BM])"
  default     = "INTEL_VM"
}

variable "instance_platform_config_virtualization_enabled" {
  type        = bool
  description = "Whether virtualization instructions are available. For example, Secure Virtual Machine for AMD shapes or VT-x for Intel shapes."
  default     = "true"
}

///////////
// Cluster node variables
///////////

variable "masters_count" {
  type        = number
  description = "The number of master nodes to be created."
}

variable "master_vcpu" {
  type        = number
  description = "Number of CPU allocated to a master node"
}

variable "master_memory_gib" {
  type        = number
  description = "Amount of memory allocated a master node"
}

variable "workers_count" {
  type        = number
  description = "The number of worker nodes to be created."
}

variable "master_disk_size_gib" {
  type        = number
  description = "Amount of disk space allocated to a master node"
}

variable "worker_vcpu" {
  type        = number
  description = "Number of CPU allocated to a worker node"
}

variable "worker_memory_gib" {
  type        = number
  description = "Amount of memory allocated to a worker node"
}

variable "worker_disk_size_gib" {
  type        = number
  description = "Amount of disk space allocated to a worker node"
}
