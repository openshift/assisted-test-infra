packer {
  required_plugins {
    nutanix = {
      version = "0.9.0"
      source  = "github.com/nutanix-cloud-native/nutanix"
    }
  }
}

# Dummy module need to be removed
# need a CI PR before removing this
source "null" "test" {
  communicator = "none"
}

build {
  sources = ["null.test"]
}