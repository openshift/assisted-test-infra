output "ci_instance_public_ip" {
  description = "CI instance public IP"
  value       = oci_core_instance.ci_instance.public_ip
}
