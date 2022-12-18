output "ip_address" {
  description = "IP"
  value       = lookup(nutanix_virtual_machine.vm.nic_list.0.ip_endpoint_list[0], "ip")
}
