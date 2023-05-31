variable "unique_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the ressource names related to the current job"
}

///////////
// OCI variables
///////////

variable "oci_compartment_id" {
  type        = string
  description = "Parent compartment where the resources will be created"
}

variable "tenancy_oicd" {
  type        = string
  description = ""
}

variable "user_oicd" {
  type        = string
  description = ""
}

variable "fingerprint" {
  type        = string
  description = ""
}

variable "private_key_path" {
  type        = string
  description = ""
}

variable "region" {
  type        = string
  description = ""
}

variable "private_ssh_key_path" {
  type        = string
  description = "Path to private key"
}

variable "public_ssh_key_path" {
  type        = string
  description = "Path to public key"
}
