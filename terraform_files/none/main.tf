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

locals {
  networks = [
    for idx in range(length(var.machine_cidr_addresses)) :
    {
      name        = "${var.libvirt_network_name}-${idx}"
      subnet      = var.machine_cidr_addresses[idx]
      interface   = var.libvirt_network_interfaces[idx]
  }]
}

resource "libvirt_pool" "storage_pool" {
  name = var.cluster_name
  type = "dir"
  path = "${var.libvirt_storage_pool_path}/${var.cluster_name}"
}

resource "libvirt_volume" "master" {
  count          = var.master_count
  name           = "${var.cluster_name}-master-${count.index}"
  pool           = libvirt_pool.storage_pool.name
  size           =  var.libvirt_master_disk
}

resource "libvirt_volume" "worker" {
  count          = var.worker_count
  name           = "${var.cluster_name}-worker-${count.index}"
  pool           = libvirt_pool.storage_pool.name
  size           =  var.libvirt_worker_disk
}

resource "libvirt_network" "net" {
  for_each  = { for idx, obj in local.networks : idx => obj }
  name      = each.value.name
  mode      = replace(each.value.subnet, ":", "") != each.value.subnet ? "nat" : "route"
  bridge    = each.value.interface
  mtu       = var.libvirt_network_mtu
  domain    = "${var.cluster_name}.${var.cluster_domain}"
  addresses = [each.value.subnet]
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
  filename = format("/etc/nginx/conf.d/stream_%s.conf", replace(var.load_balancer_ip,"/[:.]/" , "_"))
}

resource "local_file" "dns_forwarding_config" {
  count    = var.dns_forwarding_file != "" && var.dns_forwarding_file_name != "" ? 1 : 0
  content  = var.dns_forwarding_file
  filename = var.dns_forwarding_file_name
}

resource "libvirt_domain" "master" {
  count = var.master_count

  name = "${var.cluster_name}-master-${count.index}"

  memory = var.libvirt_master_memory
  vcpu   = var.libvirt_master_vcpu
  running = var.running

  disk {
    volume_id = element(libvirt_volume.master.*.id, count.index)

  }
  disk {
    file = var.image_path
  }

  console {
    type        = "pty"
    target_port = 0
  }

  cpu = {
    mode = "host-passthrough"
  }

  dynamic "network_interface" {
    for_each = { for idx, obj in local.networks : idx => obj }
    content {
      network_name = libvirt_network.net[network_interface.key].name
      hostname     = network_interface.key == 0 ? "${var.cluster_name}-net${network_interface.key}-master${count.index}.${var.cluster_domain}" : ""
      addresses    = length(var.libvirt_master_ips[count.index]) > 0 ? [var.libvirt_master_ips[count.index][network_interface.key]] : []
    }
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

  disk {
    volume_id = element(libvirt_volume.worker.*.id, count.index)
  }

  disk {
    file = var.image_path
  }

  console {
    type        = "pty"
    target_port = 0
  }

  cpu = {
    mode = "host-passthrough"
  }

  dynamic "network_interface" {
    for_each = { for idx, obj in local.networks : idx => obj if idx % 2 == count.index % 2 }
    content {
      network_name = libvirt_network.net[network_interface.key].name
      hostname     = network_interface.key == 0 ? "${var.cluster_name}-net${network_interface.key}-worker${count.index}.${var.cluster_domain}" : ""
      addresses    = length(var.libvirt_worker_ips[count.index]) > 0 ? [var.libvirt_worker_ips[count.index][network_interface.key]] : []
    }
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }

  xml {
    xslt = file("consolemodel.xsl")
  }
}
