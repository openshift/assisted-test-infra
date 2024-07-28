terraform {
  required_providers {
    equinix = {
      source = "equinix/equinix"
      version = "1.32.0"
    }
  }
}

resource "equinix_metal_device" "ci_devices" {
  for_each = { for idx, device in var.devices : idx => device }

  hostname         = each.value["hostname"]
  plan             = each.value["plan"]
  metro            = each.value["metro"]
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
      # fix for missing Python
      "dnf install python312 python3.12-pip -y || true",
      "pip3 install -U pip || true",
      # Wait for cloud-init to complete.
      # Ignore any errors because some equinix machines fail in cloud-init but
      # it is without consequenses.
      "cloud-init status --wait || true",
    ]
  }
}
