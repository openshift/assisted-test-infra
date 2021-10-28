terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
      version = "0.6.9"
    }
  }
}

provider "libvirt" {
  uri = var.libvirt_uri
}

resource "libvirt_pool" "storage_pool" {
  name = var.infra_env_name
  type = "dir"
  path = "${var.libvirt_storage_pool_path}/${var.infra_env_name}"
}

resource "libvirt_network" "net" {
  name = var.libvirt_network_name
  mode   = "nat"
  bridge = var.libvirt_network_if
  mtu = var.libvirt_network_mtu
  addresses = var.machine_cidr_addresses
  autostart = true

  dns {
    local_only = true

    dynamic "hosts" {
      for_each = var.libvirt_dns_records
      content {
        hostname = hosts.key
        ip       = hosts.value
      }
    }
  }

  xml {
    # change DHCP end range of IPv6 network to be up until IP <subnet>::63
    # that's because IPs ending with 64 and 65 are being used statically for
    # API and ingress, and libvirt terraform provider doesn't currently
    # support choosing DHCP range as a subset of the CIDR.
    # Please change the code when the following issue is done:
    # https://github.com/dmacvicar/terraform-provider-libvirt/issues/794
    xslt = file("limit_ipv6_dhcp_range.xsl")
  }
}

resource "libvirt_network" "secondary_net" {
  name = var.libvirt_secondary_network_name
  mode   = "nat"
  bridge = var.libvirt_secondary_network_if
  addresses = var.provisioning_cidr_addresses
  autostart = true
}

module "masters" {
  source            = "../baremetal_host"
  count             = var.master_count

  name              = "${var.infra_env_name}-master-${count.index}"
  memory            = var.libvirt_master_memory
  vcpu              = var.libvirt_master_vcpu
  running           = var.running
  image_path        = var.image_path
  cpu_mode          = var.master_cpu_mode
  cluster_domain    = var.infra_env_domain

  primary_network   = libvirt_network.net.name
  primary_ips       = var.libvirt_master_ips[count.index]
  primary_mac       = var.libvirt_master_macs[count.index]

  secondary_network = libvirt_network.secondary_net.name
  secondary_ips     = var.libvirt_secondary_master_ips[count.index]
  secondary_mac     = var.libvirt_secondary_master_macs[count.index]

  pool              = libvirt_pool.storage_pool.name
  disk_base_name    = "${var.infra_env_name}-master-${count.index}"
  disk_size         = var.libvirt_master_disk
  disk_count        = var.master_disk_count
}

module "workers" {
  source            = "../baremetal_host"
  count             = var.worker_count

  name              = "${var.infra_env_name}-worker-${count.index}"
  memory            = var.libvirt_worker_memory
  vcpu              = var.libvirt_worker_vcpu
  running           = var.running
  image_path        = var.image_path
  cpu_mode          = var.worker_cpu_mode
  cluster_domain    = var.infra_env_domain

  primary_network   = libvirt_network.net.name
  primary_ips       = var.libvirt_worker_ips[count.index]
  primary_mac       = var.libvirt_worker_macs[count.index]

  secondary_network = libvirt_network.secondary_net.name
  secondary_ips     = var.libvirt_secondary_worker_ips[count.index]
  secondary_mac     = var.libvirt_secondary_worker_macs[count.index]

  pool              = libvirt_pool.storage_pool.name
  disk_base_name    = "${var.infra_env_name}-worker-${count.index}"
  disk_size         = var.libvirt_worker_disk
  disk_count        = var.worker_disk_count
}

resource "local_file" "dns_forwarding_config" {
  count    = var.dns_forwarding_file != "" && var.dns_forwarding_file_name != "" ? 1 : 0
  content  = var.dns_forwarding_file
  filename = var.dns_forwarding_file_name
}
