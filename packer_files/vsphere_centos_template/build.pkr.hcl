packer {
  required_plugins {
    vsphere = {
      source  = "github.com/hashicorp/vsphere"
      version = "= 0.0.1"
    }
  }
}


build {
  sources = ["sources.vsphere-iso.basic-example"]
}