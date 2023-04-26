# Create security groups for the future cluster
# CI machine should be able to reach:
#   - LB on public IP
#   - cluster nodes in private subnet
# LB should be able to reach:
#   - cluster nodes
# cluster should be able to reach:
#   - CI machine (assisted-service/image-service)
#   - LB on internal API endpoint
# Prow should be able to reach:
#   - CI machine on SSH

# cluster NSG is hold by all clusters nodes
resource "oci_core_network_security_group" "nsg_cluster" {
  #Required
  compartment_id = var.parent_compartment_ocid
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "cluster"
}

# cluster-access is hold by LB and CI machine
resource "oci_core_network_security_group" "nsg_cluster_access" {
  #Required
  compartment_id = var.parent_compartment_ocid
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "cluster-access"
}

# all instances holding cluster-access NSG can reach cluster
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_cluster_access" {
  network_security_group_id = oci_core_network_security_group.nsg_cluster.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_cluster_access.id
  protocol                  = "all"
}

# ci-machine is hold by CI machine
resource "oci_core_network_security_group" "nsg_ci_machine" {
  #Required
  compartment_id = var.parent_compartment_ocid
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "ci-machine"
}

# ci-machine-access is hold bu cluster nodes
resource "oci_core_network_security_group" "nsg_ci_machine_access" {
  #Required
  compartment_id = var.parent_compartment_ocid
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "ci-machine-access"
}

# all instances holding ci-machine-access NSG can reach ci-machine
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_ci_machine_access" {
  network_security_group_id = oci_core_network_security_group.nsg_ci_machine.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_ci_machine_access.id
  protocol                  = "all"
}

# Allow Prow to connect on CI machine
resource "oci_core_network_security_group_security_rule" "rule_allow_from_prow_to_ci_machine" {
  network_security_group_id = oci_core_network_security_group.nsg_ci_machine.id
  direction                 = "INGRESS"
  source                    = "0.0.0.0/0"
  protocol                  = "6"
  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

# load-balancer is hold by LB
resource "oci_core_network_security_group" "nsg_load_balancer" {
  #Required
  compartment_id = var.parent_compartment_ocid
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "load-balancer"
}

# load-balancer-access is hold by cluster nodes and CI machine
resource "oci_core_network_security_group" "nsg_load_balancer_access" {
  #Required
  compartment_id = var.parent_compartment_ocid
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "load-balancer-access"
}

# all instances holding load-balancer-access NSG can reach load-balancer
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_load_balancer_access" {
  network_security_group_id = oci_core_network_security_group.nsg_load_balancer.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_load_balancer_access.id
  protocol                  = "all"
}
