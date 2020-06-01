provider "libvirt" {
  uri = var.libvirt_uri
}

resource "libvirt_network" "net" {
  name = var.libvirt_network_name

  mode   = "nat"
  bridge = var.libvirt_network_if

  domain = var.cluster_domain

  addresses = [var.machine_cidr]

  dns {
    local_only = true
    hosts  {
      ip = "{var.api_vip}"
      hostname = "api.${var.cluster_name}.${var.cluster_domain}"
    }
  }

  autostart = true
}
