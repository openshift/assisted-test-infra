provider "libvirt" {
  uri = var.libvirt_uri
}

resource "libvirt_network" "net" {
  name = "test-infra-net"

  mode   = "nat"
  bridge = var.libvirt_network_if

  domain = var.cluster_domain

  addresses = [var.machine_cidr]

  dns {
    local_only = true

    dynamic "hosts" {
      for_each = concat(
      data.libvirt_network_dns_host_template.masters.*.rendered,
      data.libvirt_network_dns_host_template.masters_int.*.rendered,
      )
      content {
        hostname = hosts.value.hostname
        ip       = hosts.value.ip
      }
    }
  }

  autostart = true
}


data "libvirt_network_dns_host_template" "masters" {
  count    = var.master_count
  ip       = var.libvirt_master_ips[count.index]
  hostname = "api.${var.cluster_domain}"
}


data "libvirt_network_dns_host_template" "masters_int" {
  count    = var.master_count
  ip       = var.libvirt_master_ips[count.index]
  hostname = "api-int.${var.cluster_domain}"
}

