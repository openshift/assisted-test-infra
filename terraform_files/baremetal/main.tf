terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.6.14"
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
  mode      = "nat"
  bridge    = var.libvirt_network_if
  mtu       = var.libvirt_network_mtu
  domain    = "${var.cluster_name}.${var.cluster_domain}"
  addresses = var.machine_cidr_addresses
  autostart = true
  dhcp {
    enabled = var.enable_dhcp
  }

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

  dnsmasq_options {
    dynamic "options" {
      for_each = concat(
        data.libvirt_network_dnsmasq_options_template.wildcard-apps-ingress.*.rendered,
      )
      content {
        option_name  = options.value.option_name
        option_value = options.value.option_value
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
  mode      = "nat"
  bridge    = var.libvirt_secondary_network_if
  addresses = var.provisioning_cidr_addresses
  autostart = true
}

module "masters" {
  source = "../baremetal_host"
  count  = var.master_count

  name           = "${var.cluster_name}-master-${count.index}"
  memory         = var.libvirt_master_memory
  vcpu           = var.libvirt_master_vcpu
  running        = var.running
  image_path     = var.image_path
  cpu_mode       = var.master_cpu_mode
  cluster_domain = var.cluster_domain
  vtpm2          = var.master_vtpm2
  boot_devices   = var.master_boot_devices

  networks = flatten([for net in [
    {
          name     = libvirt_network.net.name
          ips      = var.libvirt_master_ips
          macs     = var.libvirt_master_macs
          hostname = var.slave_interfaces ? null : "${var.cluster_name}-master-${count.index}"
    },
    {
        name     = libvirt_network.secondary_net.name
        ips      = var.libvirt_secondary_master_ips
        macs     = var.libvirt_secondary_master_macs
        hostname = null
    },
  ] : [for i in range(var.slave_interfaces ? var.network_interfaces_count : 1) :
       {
           name     = net.name
           ips      = var.slave_interfaces ? null : net.ips[count.index]
           mac      = var.slave_interfaces ? net.macs[count.index*var.network_interfaces_count+i] : net.macs[count.index]
           hostname = net.hostname
       }]])


  pool           = libvirt_pool.storage_pool.name
  disk_base_name = "${var.cluster_name}-master-${count.index}"
  disk_size      = var.libvirt_master_disk
  disk_count     = var.master_disk_count
}

module "workers" {
  source = "../baremetal_host"
  count  = var.worker_count

  name           = "${var.cluster_name}-worker-${count.index}"
  memory         = var.libvirt_worker_memory
  vcpu           = var.libvirt_worker_vcpu
  running        = var.running
  image_path     = var.worker_image_path
  cpu_mode       = var.worker_cpu_mode
  cluster_domain = var.cluster_domain
  vtpm2          = var.worker_vtpm2
  boot_devices   = var.worker_boot_devices

  networks = flatten([for net in [
    {
      name     = libvirt_network.net.name
      ips      = var.libvirt_worker_ips
      macs     = var.libvirt_worker_macs
      hostname = var.slave_interfaces ? null : "${var.cluster_name}-worker-${count.index}"
    },
    {
      name     = libvirt_network.secondary_net.name
      ips      = var.libvirt_secondary_worker_ips
      macs     = var.libvirt_secondary_worker_macs
      hostname = null
    },
  ] : [for i in range(var.slave_interfaces ? var.network_interfaces_count : 1) :
  {
    name     = net.name
    ips      = var.slave_interfaces ? null : net.ips[count.index]
    mac      = var.slave_interfaces ? net.macs[count.index*var.network_interfaces_count+i] : net.macs[count.index]
    hostname = net.hostname
  }]])

  pool           = libvirt_pool.storage_pool.name
  disk_base_name = "${var.cluster_name}-worker-${count.index}"
  disk_size      = var.libvirt_worker_disk
  disk_count     = var.worker_disk_count
}

# Define DNS entries
# Terraform doesn't have ability for conditional blocks (if cond { block }) so we're using
# the count directive to include/exclude elements

locals {
  base_cluster_domain = var.base_cluster_domain == "" ? "${var.cluster_name}.${var.cluster_domain}" : var.base_cluster_domain
}

data "libvirt_network_dns_host_template" "api" {
  # API VIP is always present. A value is set by the installation flow that updates
  # either the single node IP or API VIP, depending on the scenario
  count    = 1
  ip       = var.load_balancer_ip != "" ? var.load_balancer_ip : (var.bootstrap_in_place ? var.single_node_ip : var.api_vips[0])
  hostname = "api.${local.base_cluster_domain}"
}

data "libvirt_network_dns_host_template" "api-int" {
  count    = 1
  ip       = var.load_balancer_ip != "" ? var.load_balancer_ip : (var.bootstrap_in_place ? var.single_node_ip : var.api_vips[0])
  hostname = "api-int.${local.base_cluster_domain}"
}

# TODO: leave only the wildcard address entry defined and remove the other specific DNS assignments
# Read more at: https://bugzilla.redhat.com/show_bug.cgi?id=1532856
data "libvirt_network_dnsmasq_options_template" "wildcard-apps-ingress" {
  # Enable "apps" wildcard in case of SNO and when we try to add day2 worker to SNO
  count        = var.ingress_vips == var.api_vips ? 1 : 0
  option_name  = "address"
  option_value = "/apps.${local.base_cluster_domain}/${var.ingress_vips[0]}"
}

data "libvirt_network_dns_host_template" "oauth" {
  count    = var.master_count == 1 ? 1 : 0
  ip       = var.load_balancer_ip != "" ? var.load_balancer_ip : (var.bootstrap_in_place ? var.single_node_ip : var.ingress_vips[0])
  hostname = "oauth-openshift.apps.${local.base_cluster_domain}"
}

data "libvirt_network_dns_host_template" "console" {
  count    = var.master_count == 1 ? 1 : 0
  ip       = var.load_balancer_ip != "" ? var.load_balancer_ip : (var.bootstrap_in_place ? var.single_node_ip : var.ingress_vips[0])
  hostname = "console-openshift-console.apps.${local.base_cluster_domain}"
}

data "libvirt_network_dns_host_template" "canary" {
  count    = var.master_count == 1 ? 1 : 0
  ip       = var.load_balancer_ip != "" ? var.load_balancer_ip : (var.bootstrap_in_place ? var.single_node_ip : var.ingress_vips[0])
  hostname = "canary-openshift-ingress-canary.apps.${local.base_cluster_domain}"
}

data "libvirt_network_dns_host_template" "assisted_service" {
  # Ingress VIP is always present. A value is set by the installation flow that updates
  # either the single node IP or API VIP, depending on the scenario
  count    = 1
  ip       = var.bootstrap_in_place ? var.single_node_ip : var.ingress_vips[0]
  hostname = "assisted-service-assisted-installer.apps.${local.base_cluster_domain}"
}

resource "local_file" "load_balancer_config" {
  count    = var.load_balancer_ip != "" && var.load_balancer_config_file != "" ? 1 : 0
  content  = var.load_balancer_config_file
  filename = format("/etc/nginx/conf.d/stream_%s.conf", replace(var.load_balancer_ip, "/[:.]/", "_"))
}
