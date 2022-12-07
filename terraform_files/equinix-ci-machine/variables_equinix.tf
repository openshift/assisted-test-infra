variable "global_project_id" {
  type        = string
  description = "Project in which the devices will be created"
}

variable "global_facilities" {
  type        = list(string)
  default     = ["any"]
  description = "Metro in which the devices will be created"
}

variable "global_operating_system" {
  type        = string
  default     = "rocky_8"
  description = "Operating system that will be installed in the created devices"
}

variable "global_tags" {
  type        = list(string)
  default     = []
  description = "Global tags associated to the created devices"
}

variable "ssh_private_key_path" {
  type        = string
  description = "Path to SSH private key authorized to connect on the created devices"
}

variable "hostname_prefix" {
  type        = string
  description = "Prefix as used as hostname for the created devices"
}

variable "devices" {
  description = "The total configuration, List of Objects/Dictionary"
  type = list(
    object({
      plan             = string
      facilities       = optional(list(string), null)
      operating_system = optional(string, null)
      project_id       = optional(string, null)
      tags             = optional(list(string), [])
    })
  )
}
