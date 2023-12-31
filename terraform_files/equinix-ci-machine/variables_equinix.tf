variable "devices" {
  description = "Settings for desired devices"
  type = list(
    object({
      metros               = optional(list(string), ["any"])
      hostname             = string
      operating_system     = optional(string, "rocky_8")
      plan                 = string
      project_id           = string
      ssh_private_key_path = string
      ssh_user             = optional(string, "root")
      tags                 = optional(list(string), [])
    })
  )
}
