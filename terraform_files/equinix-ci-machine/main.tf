terraform {
  required_providers {
    equinix = {
      source = "equinix/equinix"
    }
  }
}

resource "equinix_metal_device" "ci_devices" {
  for_each = { for idx, device in var.devices : idx => device }

  hostname         = each.value["hostname"]
  plan             = each.value["plan"]
  facilities       = each.value["facilities"]
  operating_system = each.value["operating_system"]
  project_id       = each.value["project_id"]
  tags             = each.value["tags"]

  # wait an ssh connection and wait for cloud-init to complete
  connection {
    type        = "ssh"
    user        = each.value["ssh_user"]
    host        = self.access_public_ipv4
    timeout     = "5m"
    private_key = file(each.value["ssh_private_key_path"])
  }

  provisioner "remote-exec" {
    inline = [
      "cloud-init status --wait"
    ]
  }
}
