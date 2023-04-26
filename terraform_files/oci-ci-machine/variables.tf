variable "parent_compartment_ocid" {
  type        = string
  description = "Parent compartment where the resources will be created"
}

variable "private_ssh_key_path" {
  type        = string
  description = "Path to private key"

}

variable "public_ssh_key_path" {
  type        = string
  description = "Path to public key"
}

variable "unique_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the ressource names related to the current job"
}
