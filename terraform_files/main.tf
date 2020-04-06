provider "libvirt" {
  uri = var.libvirt_uri
}

resource "libvirt_pool" "storage_pool" {
  name = var.cluster_id
  type = "dir"
  path = "${var.libvirt_storage_pool_path}/${var.cluster_id}"
}

resource "libvirt_volume" "master" {
  count          = var.master_count
  name           = "${var.cluster_id}-master-${count.index}"
  pool           = libvirt_pool.storage_pool.name
  size           =  10737418240
}

resource "libvirt_volume" "worker" {
  count          = var.worker_count
  name           = "${var.cluster_id}-worker-${count.index}"
  pool           = libvirt_pool.storage_pool.name
  size           =  10737418240
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
      data.libvirt_network_dns_host_template.workers.*.rendered,
      data.libvirt_network_dns_host_template.workers_int.*.rendered,
      )
      content {
        hostname = hosts.value.hostname
        ip       = hosts.value.ip
      }
    }
  }

  autostart = true
}

resource "libvirt_domain" "master" {
  count = var.master_count

  name = "${var.cluster_id}-master-${count.index}"

  memory = var.libvirt_master_memory
  vcpu   = var.libvirt_master_vcpu

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
    network_name = "test-infra-net"
    hostname   = "${var.cluster_id}-master-${count.index}.${var.cluster_domain}"
    addresses  = [var.libvirt_master_ips[count.index]]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
}


resource "libvirt_domain" "worker" {
  count = var.worker_count

  name = "${var.cluster_id}-worker-${count.index}"

  memory = var.libvirt_worker_memory
  vcpu   = var.libvirt_worker_vcpu

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
    network_name = "test-infra-net"
    hostname   = "${var.cluster_id}-worker-${count.index}.${var.cluster_domain}"
    addresses  = [var.libvirt_worker_ips[count.index]]
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }
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

data "libvirt_network_dns_host_template" "workers" {
  count    = 1
  ip       = var.libvirt_worker_ips[count.index]
  hostname = "api.${var.cluster_domain}"
}


data "libvirt_network_dns_host_template" "workers_int" {
  count    = 1
  ip       = var.libvirt_worker_ips[count.index]
  hostname = "api-int.${var.cluster_domain}"
}