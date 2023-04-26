variable "oci_compartment_id" {
  type        = string
  description = "Parent compartment where the resources will be created"
  default     = "ocid1.compartment.oc1..aaaaaaaai7vtinyn742rxezzwu5ush25eycupetff6li2hy2zmi74zbleeka"
}

variable "private_ssh_key_path" {
  type        = string
  description = "Path to private key"
  default     = "/home/agentil/.ssh/id_ed25519"

}

variable "public_ssh_key_path" {
  type        = string
  description = "Path to public key"
  default     = "/home/agentil/.ssh/id_ed25519.pub"
}

variable "job_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the ressource names related to the current job"
  default     = "12345678901234567890"
}
