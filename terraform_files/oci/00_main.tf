terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "4.117.0"
    }
  }
}

provider "oci" {
}
