variable "devices" {
  description = "Settings for desired devices"
  type = list(
    object({
      metro                = optional(string, "da")
      hostname             = string
      operating_system     = optional(string, "rocky_9")
      plan                 = string
      project_id           = string
      ssh_private_key_path = string
      ssh_user             = optional(string, "root")
      tags                 = optional(list(string), [])
    })
  )
}
