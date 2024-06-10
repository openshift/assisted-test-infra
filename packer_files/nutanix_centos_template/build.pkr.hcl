packer {
  required_plugins {
    nutanix = {
      version = "0.9.0"
      source  = "github.com/nutanix-cloud-native/nutanix"
    }
  }
}

build {
  sources = ["sources.nutanix.test-infra"]
}
