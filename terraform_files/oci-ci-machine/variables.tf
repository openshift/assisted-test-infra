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

# List of available OSes: https://docs.oracle.com/en-us/iaas/images/oracle-linux-8x/
variable "os_image_name" {
  type        = string
  description = "Name of the OS to be provisioned on the CI machine"
  default     = "Oracle-Linux-8.7-2023.05.24-0"
}
