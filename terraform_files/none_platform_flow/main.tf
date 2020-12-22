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

resource "libvirt_volume" "secondary_master" {
  count          = var.secondary_master_count
  name           = "${var.cluster_name}-secondary-master-${count.index}"
  pool           = libvirt_pool.storage_pool.name
  size           =  var.libvirt_master_disk
}

resource "libvirt_volume" "secondary_worker" {
  count          = var.secondary_worker_count
  name           = "${var.cluster_name}-secondary-worker-${count.index}"
  pool           = libvirt_pool.storage_pool.name
  size           =  var.libvirt_worker_disk
}

resource "libvirt_network" "net" {
  name = var.libvirt_network_name
  mode   = "route"
  bridge = "virbr126"
  mtu = var.libvirt_network_mtu
  domain = var.cluster_domain
  addresses = var.machine_cidr_addresses
  autostart = true

  dns {
    dynamic "hosts" {
      for_each = concat(
      data.libvirt_network_dns_host_template.masters.*.rendered,
      data.libvirt_network_dns_host_template.masters_int.*.rendered,
      data.libvirt_network_dns_host_template.masters_console.*.rendered,
      data.libvirt_network_dns_host_template.masters_oauth.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters_int.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters_console.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters_oauth.*.rendered,
      data.libvirt_network_dns_host_template.workers.*.rendered,
      data.libvirt_network_dns_host_template.workers_int.*.rendered,
      data.libvirt_network_dns_host_template.workers_console.*.rendered,
      data.libvirt_network_dns_host_template.workers_oauth.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers_int.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers_console.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers_oauth.*.rendered
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
  mode   = "route"
  bridge = "virbr141"
  addresses = var.provisioning_cidr_addresses
  autostart = true
  mtu = var.libvirt_network_mtu
  dns {
    dynamic "hosts" {
      for_each = concat(
      data.libvirt_network_dns_host_template.masters.*.rendered,
      data.libvirt_network_dns_host_template.masters_int.*.rendered,
      data.libvirt_network_dns_host_template.masters_console.*.rendered,
      data.libvirt_network_dns_host_template.masters_oauth.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters_int.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters_console.*.rendered,
      data.libvirt_network_dns_host_template.secondary_masters_oauth.*.rendered,
      data.libvirt_network_dns_host_template.workers.*.rendered,
      data.libvirt_network_dns_host_template.workers_int.*.rendered,
      data.libvirt_network_dns_host_template.workers_console.*.rendered,
      data.libvirt_network_dns_host_template.workers_oauth.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers_int.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers_console.*.rendered,
      data.libvirt_network_dns_host_template.secondary_workers_oauth.*.rendered
      )
      content {
        hostname = hosts.value.hostname
        ip       = hosts.value.ip
      }
    }
  }
}

data "libvirt_network_dns_host_template" "masters" {
  count    = var.master_count
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_int" {
  count    = var.master_count
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_console" {
  count    = var.master_count
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "masters_oauth" {
  count    = var.master_count
  ip       = var.libvirt_master_ips[count.index][0]
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "workers" {
  count    = var.worker_count
  ip       = var.libvirt_worker_ips[count.index][0]
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "workers_int" {
  count    = var.worker_count
  ip       = var.libvirt_worker_ips[count.index][0]
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "workers_console" {
  count    = var.worker_count
  ip       = var.libvirt_worker_ips[count.index][0]
  hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "workers_oauth" {
  count    = var.worker_count
  ip       = var.libvirt_worker_ips[count.index][0]
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_masters" {
  count    = var.secondary_master_count
  ip       = var.libvirt_secondary_master_ips[count.index][0]
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_masters_int" {
  count    = var.secondary_master_count
  ip       = var.libvirt_secondary_master_ips[count.index][0]
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_masters_console" {
   count    = var.secondary_master_count
   ip       = var.libvirt_secondary_master_ips[count.index][0]
   hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_masters_oauth" {
  count    = var.secondary_master_count
  ip       = var.libvirt_secondary_master_ips[count.index][0]
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_workers" {
  count    = var.secondary_worker_count
  ip       = var.libvirt_secondary_worker_ips[count.index][0]
  hostname = "api.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_workers_int" {
  count    = var.secondary_worker_count
  ip       = var.libvirt_secondary_worker_ips[count.index][0]
  hostname = "api-int.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_workers_console" {
  count    = var.secondary_worker_count
  ip       = var.libvirt_secondary_worker_ips[count.index][0]
  hostname = "console-openshift-console.apps.${var.cluster_name}.${var.cluster_domain}"
}

data "libvirt_network_dns_host_template" "secondary_workers_oauth" {
  count    = var.secondary_worker_count
  ip       = var.libvirt_secondary_worker_ips[count.index][0]
  hostname = "oauth-openshift.apps.${var.cluster_name}.${var.cluster_domain}"
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
    network_name = libvirt_network.net.name
    hostname   = "${var.cluster_name}-worker-${count.index}.${var.cluster_domain}"
    addresses  = var.libvirt_worker_ips[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
}

resource "libvirt_domain" "secondary_master" {
  count = var.secondary_master_count

  name = "${var.cluster_name}-secondary-master-${count.index}"

  memory = var.libvirt_master_memory
  vcpu   = var.libvirt_master_vcpu
  running = var.running

  disk {
    volume_id = element(libvirt_volume.secondary_master.*.id, count.index)
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
    addresses    = var.libvirt_secondary_master_ips[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
}

resource "libvirt_domain" "secondary_worker" {
  count = var.secondary_worker_count

  name = "${var.cluster_name}-secondary-worker-${count.index}"

  memory  = var.libvirt_worker_memory
  vcpu    = var.libvirt_worker_vcpu
  running = var.running

  disk {
    volume_id = element(libvirt_volume.secondary_worker.*.id, count.index)
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
    addresses    = var.libvirt_secondary_worker_ips[count.index]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
}