terraform {
  required_providers {
    nutanix = {
      source = "nutanix/nutanix"
      version = "1.6.1"
    }
  }
}

locals {
  folder = var.nutanix_folder != "" ? var.nutanix_folder : var.cluster_name
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
  name = var.nutanix_cluster_name
}

data "nutanix_subnet" "subnet" {
  subnet_name = var.nutanix_subnet_name
}

resource "nutanix_image" "image" {
  name        = "${var.cluster_name}.iso"
  description = "Downloaded ISO"
  source_path  = var.iso_download_path
}
