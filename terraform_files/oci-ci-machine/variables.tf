variable "unique_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the ressource names related to the current job"
}

variable "private_ssh_key_path" {
  type        = string
  description = "Path to private key"
}

variable "public_ssh_key_path" {
  type        = string
  description = "Path to public key"
}

# Rocky Linux image ID
#
# Best way to find it is to spawn an instance with Rocky Linux and then copy
# the image ID that is in use. It is best to pin it, as the agreement system in
# OCI is painful to get right programmatically.
variable "operating_system_source_id" {
  type        = string
  default     = "ocid1.image.oc1..aaaaaaaauo3kyxlty6himw7uecc4xdzshdnc43qf4q2uyvy32gi3t3ixg5pa"
  description = "Base OS image ID being used to provision the CI machine"
}

///////////
// OCI variables
///////////

variable "oci_compartment_id" {
  type        = string
  description = "Parent compartment where the resources will be created"
}

variable "oci_tenancy_id" {
  type        = string
  description = "tenancy OCID authentication value"
}

variable "oci_user_id" {
  type        = string
  description = "user OCID authentication value"
}

variable "oci_fingerprint" {
  type        = string
  description = "key fingerprint authentication value"
}

variable "oci_private_key_path" {
  type        = string
  description = "private key path authentication value"
}

variable "oci_region" {
  type        = string
  description = "OCI region"
}
