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

# Check the folowing URL to update the default value:
# https://docs.oracle.com/en-us/iaas/images/oracle-linux-9x/index.htm
variable "operating_system_source_id" {
  type        = string
  default     = "ocid1.image.oc1.us-sanjose-1.aaaaaaaaizqrsucjjxtqwnbhlxmmjtkj4qeebqhipp2d6m4rovhsdjjxbmzq"
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
