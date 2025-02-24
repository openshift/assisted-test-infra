output "ci_machine_inventory" {
  value = {
    "public_ip" : oci_core_instance.ci_instance.public_ip,
    "display_name" : oci_core_instance.ci_instance.display_name,
    "ssh_private_key_path" : var.private_ssh_key_path,
    "user" : "root",
  }
}
