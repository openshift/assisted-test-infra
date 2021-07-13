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
  name = var.libvirt_network_name
  mode   = length(var.machine_cidr_addresses) == 1 && replace(var.machine_cidr_addresses[0], ":", "") != var.machine_cidr_addresses[0] ? "nat" : "route"
  bridge = var.libvirt_network_if
  mtu = var.libvirt_network_mtu
  domain = var.cluster_domain
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
}

resource "libvirt_network" "secondary_net" {
  name = var.libvirt_secondary_network_name
  mode   = length(var.provisioning_cidr_addresses) == 1 && replace(var.provisioning_cidr_addresses[0], ":", "") != var.provisioning_cidr_addresses[0] ? "nat" : "route"
  bridge = var.libvirt_secondary_network_if
  addresses = var.provisioning_cidr_addresses
  mtu = var.libvirt_network_mtu
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
  count = 2

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

  network_interface {
    network_name = libvirt_network.net.name
    hostname   = "${var.cluster_name}-master-${count.index}.${var.cluster_domain}"
    addresses  = var.libvirt_master_ips[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
}


resource "libvirt_domain" "master-sec" {
  count = 1

  name = "${var.cluster_name}-master-sec-${count.index}"

  memory = var.libvirt_master_memory
  vcpu   = var.libvirt_master_vcpu
  running = var.running

  disk {
    volume_id = element(libvirt_volume.master.*.id, 2)

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

  network_interface {
    network_name = libvirt_network.secondary_net.name
    hostname   = "${var.cluster_name}-master-${count.index}-secondary.${var.cluster_domain}"
    addresses  = var.libvirt_secondary_master_ips[0]
  }

  boot_device{
    dev = ["hd", "cdrom"]
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

  network_interface {
    network_name = count.index % 2 == 0 ? libvirt_network.net.name : libvirt_network.secondary_net.name
    hostname   = "${var.cluster_name}-worker-${count.index}.${var.cluster_domain}"
    addresses  = count.index % 2 == 0 ? var.libvirt_worker_ips[count.index] : var.libvirt_secondary_worker_ips[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
}
