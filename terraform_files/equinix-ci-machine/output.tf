output "inventory" {
  value = [for d in equinix_metal_device.ci_devices : {
    "access_private_ipv4" : d.access_private_ipv4,
    "access_public_ipv4" : d.access_public_ipv4
    "hostname" : d.hostname,
    "tags" : d.tags,
    }
  ]
}
