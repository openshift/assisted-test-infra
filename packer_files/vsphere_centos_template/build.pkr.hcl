packer {
  required_plugins {
    vsphere = {
      source  = "github.com/hashicorp/vsphere"
      version = "= 1.0.3"
    }
  }
}


build {
  sources = ["sources.vsphere-iso.test-infra-template"]
}
