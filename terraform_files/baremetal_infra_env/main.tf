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
  name = var.infra_env_name
  type = "dir"
  path = "${var.libvirt_storage_pool_path}/${var.infra_env_name}"
}

locals {
  worker_names = [
    for pair in setproduct(range(var.worker_count), range(var.worker_disk_count)) :
      "${var.infra_env_name}-worker-${pair[0]}-disk-${pair[1]}"
  ]
  master_names = [
    for pair in setproduct(range(var.master_count), range(var.master_disk_count)) :
      "${var.infra_env_name}-master-${pair[0]}-disk-${pair[1]}"
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
  addresses = var.machine_cidr_addresses
  autostart = true

  dns {
    local_only = true

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

  name = "${var.infra_env_name}-master-${count.index}"

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
    hostname   = "${var.infra_env_name}-master-${count.index}.${var.infra_env_domain}"
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

  name = "${var.infra_env_name}-worker-${count.index}"

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
    hostname   = "${var.infra_env_name}-worker-${count.index}.${var.infra_env_domain}"
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


resource "local_file" "dns_forwarding_config" {
  count    = var.dns_forwarding_file != "" && var.dns_forwarding_file_name != "" ? 1 : 0
  content  = var.dns_forwarding_file
  filename = var.dns_forwarding_file_name
}
