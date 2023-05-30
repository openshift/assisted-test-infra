variable "cluster_name" {
  type        = string
  description = <<EOF
Assisted installer cluster name
All the resources will be located under a folder with this name
and tagged with the cluster name
The resources should be associate with this name for easy recognition.
EOF
}

variable "discovery_image_path" {
  type        = string
  description = "Path to the discovery ISO"
}

///////////
// OCI variables
///////////

variable "oci_compartment_id" {
  type        = string
  description = "Parent compartment where the resources will be created"
  default     = "ocid1.compartment.oc1..aaaaaaaai7vtinyn742rxezzwu5ush25eycupetff6li2hy2zmi74zbleeka"
}

variable "oci_dns_zone_name" {
  type        = string
  description = "DNS zone name where the records for the cluster will be created"
  default     = "assisted-ci.oci-rhelcert.edge-sro.rhecoeng.com"
}

variable "oci_vcn_id" {
  type        = string
  description = "VCN ID where the cluster will be created"
}

variable "oci_private_subnet_id" {
  type        = string
  description = "Subnet ID of the private subnet"
}

variable "oci_public_subnet_id" {
  type        = string
  description = "Subnet ID of the public subnet"
}

variable "oci_extra_node_nsg_ids" {
  type        = list(string)
  description = "Extra network security group IDs be assigned to cluster nodes (e.g.: to allow nodes to reach assisted service or allow SSH access to nodes)"
  default     = []
}

variable "oci_extra_load_balancer_nsg_ids" {
  type        = list(string)
  description = "Extra network security group IDs be assigned to load balancer (e.g.: to allow API/MCS/HTTP/HTTPS access to the cluster)"
  default     = []
}

///////////
// Cluster node variables
///////////

variable "masters_count" {
  type        = number
  description = "The number of master nodes to be created."
  default     = 3
}

variable "master_instance_cpu_count" {
  type        = number
  description = "Number of CPU allocated to a master node"
  default     = 4
}

variable "master_instance_memory_gb" {
  type        = number
  description = "Amount of memory allocated a master node"
  default     = 16
}

variable "workers_count" {
  type        = number
  description = "The number of worker nodes to be created."
  default     = 2
}

variable "master_instance_disk_size_gb" {
  type        = number
  description = "Amount of disk space allocated to a master node"
  default     = 100
}

variable "worker_instance_cpu_count" {
  type        = number
  description = "Number of CPU allocated to a worker node"
  default     = 2
}

variable "worker_instance_memory_gb" {
  type        = number
  description = "Amount of memory allocated to a worker node"
  default     = 8
}

variable "worker_instance_disk_size_gb" {
  type        = number
  description = "Amount of disk space allocated to a worker node"
  default     = 100
}
