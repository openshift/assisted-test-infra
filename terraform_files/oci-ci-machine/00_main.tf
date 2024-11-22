terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "6.23.0"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "2.3.2"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.oci_tenancy_id
  user_ocid        = var.oci_user_id
  fingerprint      = var.oci_fingerprint
  private_key_path = var.oci_private_key_path
  region           = var.oci_region
}
