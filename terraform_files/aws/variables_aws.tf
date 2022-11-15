variable "aws_vpc" {
  type        = string
  description = "VPC"
  default     = "vpc-0cfce97ee90c54fb1"
}

variable "aws_subnet" {
  type        = string
  description = "private subnet"
  default     = "subnet-08a826b57afed75ee"
}

variable "ipxe_ami_us_east_1" {
  type        = string
  description = "iPXE AMI in us-east-1"
  default     = "ami-0a49750c91c7e5031"
}

variable "job_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the ressource names related to the current job"
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

// Inject iPXE script into user-data
// #!ipxe
// dhcp
// chain http://boot.ipxe.org/demo/boot.php
variable "ipxe_script" {
  type        = string
  description = "ipxe script"
}

///////////
// Control Plane machine variables
///////////

variable "masters_count" {
  type        = number
  description = "The number of master nodes to be created."
}

variable "master_instance_type" {
  type        = string
  description = "instance type for masters"
  default     = "t3.xlarge"
}

variable "workers_count" {
  type        = number
  description = "The number of worker nodes to be created."
}

variable "worker_instance_type" {
  type        = string
  description = "instance type for workers"
  default     = "t3.large"
}
