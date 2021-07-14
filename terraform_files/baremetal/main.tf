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
  name = var.cluster_name
  type = "dir"
  path = "${var.libvirt_storage_pool_path}/${var.cluster_name}"
}

locals {
  worker_names = [
    for pair in setproduct(range(var.worker_count), range(var.worker_disk_count)) :
      "${var.cluster_name}-worker-${pair[0]}-disk-${pair[1]}"
  ]
  master_names = [
    for pair in setproduct(range(var.master_count), range(var.master_disk_count)) :
      "${var.cluster_name}-master-${pair[0]}-disk-${pair[1]}"
  ]
}

resource "libvirt_volume" "master" {
  for_each       = {for idx, obj in local.master_names: idx => obj}
  name           = each.value
  pool           = libvirt_pool.storage_pool.name
  size           =  var.libvirt_master_disk
}

resource "libvirt_volume" "worker" {
  for_each       = {for idx, obj in local.worker_names: idx => obj}
  name           = each.value
  pool           = libvirt_pool.storage_pool.name
  size           = var.libvirt_worker_disk
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

resource "libvirt_domain" "master" {
  count = var.master_count

  name = "${var.cluster_name}-master-${count.index}"

  memory = var.libvirt_master_memory
  vcpu   = var.libvirt_master_vcpu
  running = var.running

  dynamic "disk" {
    for_each = {
      for idx, disk in libvirt_volume.master : idx => disk.id if length(regexall(".*-master-${count.index}-disk-.*", disk.name)) > 0
    }
    content {
      volume_id = disk.value
    }
  }

  disk {
    file = var.image_path
  }

  console {
    type        = "pty"
    target_port = 0
  }

  cpu = {
    mode = var.master_cpu_mode
  }

  network_interface {
    network_name = libvirt_network.net.name
    hostname   = "${var.cluster_name}-master-${count.index}.${var.cluster_domain}"
    addresses  = var.libvirt_master_ips[count.index]
    mac = var.libvirt_master_macs[count.index]
  }
   
  network_interface {
    network_name = libvirt_network.secondary_net.name
    addresses = var.libvirt_secondary_master_ips[count.index]
    mac = var.libvirt_secondary_master_macs[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }

  xml {
    xslt = file("consolemodel.xsl")
  }
}


resource "libvirt_domain" "worker" {
  count = var.worker_count

  name = "${var.cluster_name}-worker-${count.index}"

  memory = var.libvirt_worker_memory
  vcpu   = var.libvirt_worker_vcpu
  running = var.running

  dynamic "disk" {
    for_each = {
      for idx, disk in libvirt_volume.worker : idx => disk.id if length(regexall(".*-worker-${count.index}-disk-.*", disk.name)) > 0
    }
    content {
      volume_id = disk.value
    }
  }

  disk {
    file = var.image_path
  }

  console {
    type        = "pty"
    target_port = 0
  }

  cpu = {
    mode = var.worker_cpu_mode
  }

  network_interface {
    network_name = libvirt_network.net.name
    hostname   = "${var.cluster_name}-worker-${count.index}.${var.cluster_domain}"
    addresses  = var.libvirt_worker_ips[count.index]
    mac = var.libvirt_worker_macs[count.index]
  }

  network_interface {
    network_name = libvirt_network.secondary_net.name
    addresses  = var.libvirt_secondary_worker_ips[count.index]
    mac = var.libvirt_secondary_worker_macs[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }

  xml {
    xslt = file("consolemodel.xsl")
  }
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
