terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.8.1"
    }
  }
}

provider "libvirt" {
  uri = var.libvirt_uri
}

resource "libvirt_pool" "storage_pool" {
  name = var.cluster_name
  type = "dir"
  path = "${var.libvirt_storage_pool_path}/${var.cluster_name}"
}

resource "libvirt_network" "net" {
  name      = var.libvirt_network_name
  mode      = length(var.machine_cidr_addresses) == 1 && replace(var.machine_cidr_addresses[0], ":", "") != var.machine_cidr_addresses[0] ? "nat" : "route"
  bridge    = var.libvirt_network_if
  mtu       = var.libvirt_network_mtu
  domain    = "${var.cluster_name}.${var.cluster_domain}"
  addresses = var.machine_cidr_addresses
  autostart = true

  dns {
    local_only = true
    dynamic "hosts" {
      for_each = concat(
        data.libvirt_network_dns_host_template.masters.*.rendered,
        data.libvirt_network_dns_host_template.masters_int.*.rendered,
        data.libvirt_network_dns_host_template.masters_console.*.rendered,
        data.libvirt_network_dns_host_template.masters_canary.*.rendered,
        data.libvirt_network_dns_host_template.masters_oauth.*.rendered,
      )
      content {
        hostname = hosts.value.hostname
        ip       = hosts.value.ip
      }
    }
  }

  xml {
    # change DHCP end range of IPv6 network to be up until IP <subnet>::63
    # that's because IPs ending with 64 and 65 are being used statically for
    # API and ingress, and libvirt terraform provider doesn't currently
    # support choosing DHCP range as a subset of the CIDR.
    # (mko) For the same reason we change range for IPv4 network. Because we
    # hardcode API and Ingress VIPs, it happens at times that they collide.
    # Please change the code when the following issue is done:
    # https://github.com/dmacvicar/terraform-provider-libvirt/issues/794

    xslt = file("../limit_ip_dhcp_range.xsl")
  }
}

resource "libvirt_network" "secondary_net" {
  name      = var.libvirt_secondary_network_name
  mode      = length(var.provisioning_cidr_addresses) == 1 && replace(var.provisioning_cidr_addresses[0], ":", "") != var.provisioning_cidr_addresses[0] ? "nat" : "route"
  bridge    = var.libvirt_secondary_network_if
  addresses = var.provisioning_cidr_addresses
  mtu       = var.libvirt_network_mtu
  autostart = true
  dns {
    local_only = true
    dynamic "hosts" {
      for_each = concat(
        data.libvirt_network_dns_host_template.masters.*.rendered,
        data.libvirt_network_dns_host_template.masters_int.*.rendered,
        data.libvirt_network_dns_host_template.masters_console.*.rendered,
        data.libvirt_network_dns_host_template.masters_canary.*.rendered,
        data.libvirt_network_dns_host_template.masters_oauth.*.rendered,
      )
      content {
        hostname = hosts.value.hostname
        ip       = hosts.value.ip
      }
    }
  }
}

module "masters" {
  source = "../baremetal_host"
  count  = var.master_count

  name           = count.index % 2 == 0 ? "${var.cluster_name}-master-${count.index}" : "${var.cluster_name}-master-secondary-${count.index}"
  memory         = var.libvirt_master_memory
  vcpu           = var.libvirt_master_vcpu
  running        = var.running
  image_path     = var.image_path
  cluster_domain = var.cluster_domain
  vtpm2          = var.master_vtpm2

  networks = [
    {
      name     = count.index % 2 == 0 ? libvirt_network.net.name : libvirt_network.secondary_net.name
      hostname = count.index % 2 == 0 ? "${var.cluster_name}-master-${count.index}" : "${var.cluster_name}-master-secondary-${count.index}"
      ips      = count.index % 2 == 0 ? var.libvirt_master_ips[count.index] : var.libvirt_secondary_master_ips[count.index]
      mac      = var.libvirt_master_macs[count.index]
    }
  ]

  pool           = libvirt_pool.storage_pool.name
  disk_base_name = "${var.cluster_name}-master-${count.index}"
  disk_size      = var.libvirt_master_disk
  disk_count     = var.master_disk_count
  uefi_boot_firmware = var.uefi_boot_firmware
  uefi_boot_template = var.uefi_boot_template
}

module "workers" {
  source = "../baremetal_host"
  count  = var.worker_count

  name           = count.index % 2 == 0 ? "${var.cluster_name}-worker-${count.index}" : "${var.cluster_name}-worker-secondary-${count.index}"
  memory         = var.libvirt_worker_memory
  vcpu           = var.libvirt_worker_vcpu
  running        = var.running
  image_path     = var.worker_image_path
  cluster_domain = var.cluster_domain
  vtpm2          = var.worker_vtpm2

  networks = [
    {
      name     = count.index % 2 == 0 ? libvirt_network.net.name : libvirt_network.secondary_net.name
      hostname = "${var.cluster_name}-worker-${count.index}"
      ips      = count.index % 2 == 0 ? var.libvirt_worker_ips[count.index] : var.libvirt_secondary_worker_ips[count.index]
      mac      = var.libvirt_worker_macs[count.index]
    }
  ]

  pool           = libvirt_pool.storage_pool.name
  disk_base_name = "${var.cluster_name}-worker-${count.index}"
  disk_size      = var.libvirt_worker_disk
  disk_count     = var.worker_disk_count
  uefi_boot_firmware = var.uefi_boot_firmware
  uefi_boot_template = var.uefi_boot_template
}

data "libvirt_network_dns_host_template" "masters" {
  count    = var.load_balancer_ip != "" ? 1 : 0
  ip       = var.load_balancer_ip
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_int" {
  count    = var.load_balancer_ip != "" ? 1 : 0
  ip       = var.load_balancer_ip
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_console" {
  count    = var.load_balancer_ip != "" ? 1 : 0
  ip       = var.load_balancer_ip
  hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_canary" {
  count    = var.load_balancer_ip != "" ? 1 : 0
  ip       = var.load_balancer_ip
  hostname = "canary-openshift-ingress-canary.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_oauth" {
  count    = var.load_balancer_ip != "" ? 1 : 0
  ip       = var.load_balancer_ip
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
}

resource "local_file" "load_balancer_config" {
  count    = var.load_balancer_ip != "" && var.load_balancer_config_file != "" ? 1 : 0
  content  = var.load_balancer_config_file
  filename = format("/etc/nginx/conf.d/stream_%s.conf", replace(var.load_balancer_ip, "/[:.]/", "_"))
}
