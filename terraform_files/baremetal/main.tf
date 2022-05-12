terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
      version = "0.6.12"
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
  name = var.libvirt_network_name
  mode   = "nat"
  bridge = var.libvirt_network_if
  mtu = var.libvirt_network_mtu
  domain = "${var.cluster_name}.${var.cluster_domain}"
  addresses = var.machine_cidr_addresses
  autostart = true

  dns {
    local_only = true
    dynamic "hosts" {
      for_each = concat(
        data.libvirt_network_dns_host_template.api.*.rendered,
        data.libvirt_network_dns_host_template.api-int.*.rendered,
        data.libvirt_network_dns_host_template.oauth.*.rendered,
        data.libvirt_network_dns_host_template.console.*.rendered,
        data.libvirt_network_dns_host_template.canary.*.rendered,
        data.libvirt_network_dns_host_template.assisted_service.*.rendered,
      )
      content {
        hostname = hosts.value.hostname
        ip       = hosts.value.ip
      }
    }

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

  name              = "${var.cluster_name}-master-${count.index}"
  memory            = var.libvirt_master_memory
  vcpu              = var.libvirt_master_vcpu
  running           = var.running
  image_path        = var.image_path
  cpu_mode          = var.master_cpu_mode
  cluster_domain    = var.cluster_domain
  vtpm2             = var.master_vtpm2
  boot_devices      = var.master_boot_devices
  
  networks          = [
                        {
                          name     = libvirt_network.net.name
                          hostname = "${var.cluster_name}-master-${count.index}"
                          ips      = var.libvirt_master_ips[count.index]
                          mac      = var.libvirt_master_macs[count.index]
                        },
                        {
                          name     = libvirt_network.secondary_net.name
                          ips      = var.libvirt_secondary_master_ips[count.index]
                          mac      = var.libvirt_secondary_master_macs[count.index]
                        },
                      ]

  pool              = libvirt_pool.storage_pool.name
  disk_base_name    = "${var.cluster_name}-master-${count.index}"
  disk_size         = var.libvirt_master_disk
  disk_count        = var.master_disk_count
}

module "workers" {
  source            = "../baremetal_host"
  count             = var.worker_count

  name              = "${var.cluster_name}-worker-${count.index}"
  memory            = var.libvirt_worker_memory
  vcpu              = var.libvirt_worker_vcpu
  running           = var.running
  image_path        = var.worker_image_path
  cpu_mode          = var.worker_cpu_mode
  cluster_domain    = var.cluster_domain
  vtpm2             = var.worker_vtpm2
  boot_devices      = var.worker_boot_devices
  
  networks          = [
                        {
                          name     = libvirt_network.net.name
                          hostname = "${var.cluster_name}-worker-${count.index}"
                          ips      = var.libvirt_worker_ips[count.index]
                          mac      = var.libvirt_worker_macs[count.index]
                        },
                        {
                          name     = libvirt_network.secondary_net.name
                          ips      = var.libvirt_secondary_worker_ips[count.index]
                          mac      = var.libvirt_secondary_worker_macs[count.index]
                        },
                      ]

  pool              = libvirt_pool.storage_pool.name
  disk_base_name    = "${var.cluster_name}-worker-${count.index}"
  disk_size         = var.libvirt_worker_disk
  disk_count        = var.worker_disk_count
}

# Define DNS entries
# Terraform doesn't have ability for conditional blocks (if cond { block }) so we're using
# the count directive to include/exclude elements

data "libvirt_network_dns_host_template" "api" {
  # API VIP is always present. A value is set by the installation flow that updates
  # either the single node IP or API VIP, depending on the scenario
  count    = 1
  ip       = var.bootstrap_in_place ? var.single_node_ip : var.api_vip
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "api-int" {
  count    = var.bootstrap_in_place ? 1 : 0
  ip       = var.single_node_ip
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

# TODO: Move to use wildcard with dnsmasq options
# Read more at: https://bugzilla.redhat.com/show_bug.cgi?id=1532856
# terraform-libvirt-provider supports dnsmasq options since https://github.com/dmacvicar/terraform-provider-libvirt/pull/820
# but there's still no an official release with that code.
data "libvirt_network_dns_host_template" "oauth" {
  count    = var.bootstrap_in_place ? 1 : 0
  ip       = var.single_node_ip
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "console" {
  count    = var.bootstrap_in_place ? 1 : 0
  ip       = var.single_node_ip
  hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "canary" {
  count    = var.bootstrap_in_place ? 1 : 0
  ip       = var.single_node_ip
  hostname = "canary-openshift-ingress-canary.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "assisted_service" {
  # Ingress VIP is always present. A value is set by the installation flow that updates
  # either the single node IP or API VIP, depending on the scenario
  count    = 1
  ip       = var.bootstrap_in_place ? var.single_node_ip : var.ingress_vip
  hostname = "assisted-service-assisted-installer.apps.${var.cluster_name}.${var.cluster_domain}"
}

resource "local_file" "dns_forwarding_config" {
  count    = var.dns_forwarding_file != "" && var.dns_forwarding_file_name != "" ? 1 : 0
  content  = var.dns_forwarding_file
  filename = var.dns_forwarding_file_name
}
