terraform {
  required_providers {
    nutanix = {
      source  = "nutanix/nutanix"
      version = "1.9.5"
    }
  }
}

provider "nutanix" {
  username     = var.nutanix_username
  password     = var.nutanix_password
  endpoint     = var.nutanix_endpoint
  port         = var.nutanix_port
  insecure     = true
  wait_timeout = 60
  session_auth = false
}

data "nutanix_cluster" "cluster" {
  name = var.nutanix_cluster
}

data "nutanix_subnet" "subnet" {
  subnet_name = var.nutanix_subnet
}

resource "nutanix_image" "cloud_image" {
  name        = "rocky9"
  source_uri  = var.cloud_image_url
}

resource "local_file" "cloud_config" {
  filename = var.cloud_config_file
  content  = <<EOF
#cloud-config
ssh_pwauth: True
disable_root: False
users:
  - name: root
    plain_text_passwd: packer
    lock_passwd: False
    ssh_authorized_keys:
      - ${var.ssh_public_key}
    ssh_keys:
      rsa_private: "${var.ssh_private_key}"
      rsa_public:  ${var.ssh_public_key}
write_files:
- content: |
    PermitRootLogin yes
  path: /etc/ssh/sshd_config
  append: true
growpart:
  devices: [/]
  ignore_growroot_disabled: false
  mode: auto
runcmd:
  - update-crypto-policies --set DEFAULT:SHA1
  - systemctl enable --now sshd
  - systemctl restart sshd
  - set enforce 0 sestatus
  - timedatectl set-timezone America/New_York
EOF
}

data "local_file" "cloud_config_file" {
  filename = "${var.cloud_config_file}"
  depends_on = [
    local_file.cloud_config
  ]
}

resource "nutanix_virtual_machine" "vm" {
  name                 = "assisted-ci-build-${var.build_id}"
  cluster_uuid         = data.nutanix_cluster.cluster.id
  num_vcpus_per_socket = var.cores_per_socket
  memory_size_mib      = var.memory
  num_sockets          = var.vcpu
  guest_customization_cloud_init_user_data = "${data.local_file.cloud_config_file.content_base64}"

  boot_device_order_list = ["DISK"]
  boot_type              = "LEGACY"

  enable_cpu_passthrough = true

  disk_list {
    data_source_reference = {
      kind = "image"
      uuid = nutanix_image.cloud_image.id
    }
    disk_size_bytes = var.disk_size * 1024 * 1024 * 1024
  }

  nic_list {
    subnet_uuid = data.nutanix_subnet.subnet.id
  }

}
