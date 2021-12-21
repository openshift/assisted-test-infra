terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
      version = "0.6.12"
    }
  }
}

locals {
  disk_names = [
    for index in range(var.disk_count):
      "${var.disk_base_name}-disk-${index}"
  ]
}

resource "libvirt_domain" "host" {
  name = var.name

  memory = var.memory
  vcpu   = var.vcpu
  running = var.running

  dynamic "disk" {
    for_each = {
      for idx, disk in libvirt_volume.host : idx => disk.id if length(regexall("${var.disk_base_name}-disk-.*", disk.name)) > 0
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

  cpu {
    mode = var.cpu_mode
  }

  network_interface {
    network_name = var.primary_network
    hostname   = "${var.name}.${var.cluster_domain}"
    addresses  = var.primary_ips
    mac = var.primary_mac
  }

  network_interface {
    network_name = var.secondary_network
    addresses  = var.secondary_ips
    mac = var.secondary_mac
  }

  boot_device{
    dev = ["hd", "cdrom"]
  }

  dynamic "tpm" {
    for_each = var.vtpm2 ? [1] : []

    content {
      backend_type    = "emulator"
      backend_version = "2.0"
    }
  }

  xml {
    xslt = file("consolemodel.xsl")
  }
}

resource "libvirt_volume" "host" {
  for_each = {for idx, obj in local.disk_names: idx => obj}
  name     = each.value
  pool     = var.pool
  size     = var.disk_size
}
