output "ip_address" {
  description = "IP"
  value       = vsphere_virtual_machine.vm.default_ip_address
}