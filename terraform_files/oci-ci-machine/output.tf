output "ci_machine_inventory" {
  value = {
    "public_ip" : oci_core_instance.ci_instance.public_ip,
    "display_name" : oci_core_instance.ci_instance.display_name,
    "ssh_private_key_path" : var.private_ssh_key_path,
    "user" : "root",
  }
}

output "infra" {
  value = {
    "oci_vcn_id" : module.vcn.vcn_id,
    "oci_private_subnet_id" : oci_core_subnet.vcn_private_subnet.id,
    "oci_public_subnet_id" : oci_core_subnet.vcn_public_subnet.id,
    "oci_iscsi_subnet_id" : oci_core_subnet.vcn_iscsi_subnet.id,
    "oci_ci_machine_access_nsg_id" : oci_core_network_security_group.nsg_ci_machine_access.id,
    "oci_cluster_ci_nsg_id" : oci_core_network_security_group.nsg_cluster_ci.id,
    "oci_load_balancer_ci_nsg_id" : oci_core_network_security_group.nsg_load_balancer_ci.id
  }
}
