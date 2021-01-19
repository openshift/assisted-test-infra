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
    mac = var.libvirt_master_macs[count.index]
  }
   
  dynamic "network_interface" {
    for_each = var.bootstrap_in_place ? [] : ["secondary_net"]
    content {
      network_name = libvirt_network.secondary_net.name
      addresses = var.libvirt_secondary_master_ips[count.index]
      mac = var.libvirt_secondary_master_macs[count.index]
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
  count    = !var.bootstrap_in_place || length(var.libvirt_master_ips[0]) > 0 ? 1 : 0
  ip       = var.bootstrap_in_place ? var.libvirt_master_ips[count.index][0] : var.api_vip
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "api-int" {
  count    = var.bootstrap_in_place && length(var.libvirt_master_ips[0]) > 0 ? 1 : 0
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "oauth" {
  count    = var.bootstrap_in_place && length(var.libvirt_master_ips[0]) > 0 ? 1 : 0
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "console" {
  count    = var.bootstrap_in_place && length(var.libvirt_master_ips[0]) > 0 ? 1 : 0
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}
