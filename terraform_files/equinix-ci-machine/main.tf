terraform {
  required_providers {
    equinix = {
      source = "equinix/equinix"
    }
  }
}

resource "equinix_metal_device" "ci_devices" {
  for_each = { for idx, device in var.devices : idx => device }

  hostname         = "${var.hostname_prefix}-${each.key}"
  plan             = each.value["plan"]
  facilities       = each.value["facilities"] != null ? each.value["facilities"] : var.global_facilities
  operating_system = each.value["operating_system"] != null ? each.value["operating_system"] : var.global_operating_system
  project_id       = each.value["project_id"] != null ? each.value["project_id"] : var.global_project_id
  tags             = concat(var.global_tags, each.value["tags"])

  # wait an ssh connection and wait for cloud-init to complete
  connection {
    type        = "ssh"
    user        = "root"
    host        = self.access_public_ipv4
    timeout     = "5m"
    private_key = file(var.ssh_private_key_path)
  }

  provisioner "remote-exec" {
    inline = [
      "cloud-init status --wait"
    ]
  }

}
