packer {
  required_plugins {
    vsphere = {
      source  = "github.com/hashicorp/vsphere"
      version = "= 1.3.0"
    }
  }
}


build {
  sources = ["sources.vsphere-iso.test-infra-template"]
}
