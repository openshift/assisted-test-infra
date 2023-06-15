terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "4.122.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.oci_tenancy_oicd
  user_ocid        = var.oci_user_oicd
  fingerprint      = var.oci_key_fingerprint
  private_key_path = var.oci_private_key_path
  region           = var.oci_region
}
