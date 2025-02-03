terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.8.1"
    }
  }
}

locals {
  disk_names = [
    for index in range(var.disk_count) :
    "${var.disk_base_name}-disk-${index}"
  ]
}

resource "libvirt_domain" "host" {
  name = var.name

  memory  = var.memory
  vcpu    = var.vcpu
  running = var.running

  dynamic "disk" {
    for_each = {
      for idx, disk in libvirt_volume.host : idx => disk.id if length(regexall("${var.disk_base_name}-disk-.*", disk.name)) > 0
    }
    content {
      volume_id = disk.value
      scsi      = true
    }
  }

  disk {
    file = var.image_path
    # Set scsi to true here for documentation purpose
    # as cdrom drive is always set to ide (at least up to 0.7.1).
    # The bus is actually updated through the xsl sheet.
    scsi = true
  }

  console {
    type        = "pty"
    target_port = 0
  }

  cpu {
    mode = var.cpu_mode
  }

  dynamic "network_interface" {
    for_each = var.networks
    content {
      network_name = network_interface.value.name
      hostname     = network_interface.value.hostname
      addresses    = network_interface.value.ips
      mac          = network_interface.value.mac
    }
  }

  boot_device {
    dev = var.boot_devices
  }

  graphics {
    type           = "vnc"
    listen_type    = "address"
    listen_address = "127.0.0.1"
    autoport       = true
  }

  dynamic "tpm" {
    for_each = var.vtpm2 ? [1] : []

    content {
      backend_type    = "emulator"
      backend_version = "2.0"
    }
  }

  xml {
    xslt = file("../baremetal_host/libvirt_domain_custom.xsl")
  }
}

resource "libvirt_volume" "host" {
  for_each = { for idx, obj in local.disk_names : idx => obj }
  name     = each.value
  pool     = var.pool
  size     = var.disk_size
}
