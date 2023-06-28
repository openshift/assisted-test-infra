# Create security groups for the future cluster
# CI machine should be able to reach:
#   - LB on public IP
#   - cluster nodes in private subnet (SSH)
# cluster nodes should be able to reach:
#   - CI machine (assisted-service/image-service)
# Prow should be able to reach:
#   - CI machine on SSH

# cluster NSG is hold by all clusters nodes
resource "oci_core_network_security_group" "nsg_cluster_ci" {
  #Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "cluster-ci"
}

# cluster-access is hold by LB and CI machine
resource "oci_core_network_security_group" "nsg_cluster_ci_access" {
  #Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "cluster-ci-access"
}

# all instances holding cluster-access NSG can reach cluster
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_cluster_ci_access" {
  network_security_group_id = oci_core_network_security_group.nsg_cluster_ci.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_cluster_ci_access.id
  protocol                  = "all"
}

# ci-machine is hold by CI machine
resource "oci_core_network_security_group" "nsg_ci_machine" {
  #Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "ci-machine"
}

# ci-machine-access is hold bu cluster nodes
resource "oci_core_network_security_group" "nsg_ci_machine_access" {
  #Required
  compartment_id = var.oci_compartment_id
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
resource "oci_core_network_security_group" "nsg_load_balancer_ci" {
  #Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "load-balancer-ci"
}

# load-balancer-access is hold by cluster nodes and CI machine
resource "oci_core_network_security_group" "nsg_load_balancer_ci_access" {
  #Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  #Optional
  display_name = "load-balancer-ci-access"
}

# all instances holding load-balancer-access NSG can reach load-balancer
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_load_balancer_access" {
  network_security_group_id = oci_core_network_security_group.nsg_load_balancer_ci.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_load_balancer_ci_access.id
  protocol                  = "all"
}

locals {
  nat_ip = one([for attr in module.vcn.nat_gateway_all_attributes : attr.nat_ip])
}

# ci-machine reach load-balancer with its public IP
resource "oci_core_network_security_group_security_rule" "rule_allow_from_public_ci_machine" {
  network_security_group_id = oci_core_network_security_group.nsg_load_balancer_ci.id
  description               = "Allow traffic from ci-machine"
  direction                 = "INGRESS"
  source_type               = "CIDR_BLOCK"
  source                    = "${oci_core_instance.ci_instance.public_ip}/32"
  protocol                  = "all"
}

# all private instances behind NAT can reach load-balancer
resource "oci_core_network_security_group_security_rule" "rule_allow_from_public_nat_gateway" {
  network_security_group_id = oci_core_network_security_group.nsg_load_balancer_ci.id
  description               = "Allow traffic from NAT gateway"
  direction                 = "INGRESS"
  source_type               = "CIDR_BLOCK"
  source                    = "${local.nat_ip}/32"
  protocol                  = "all"
}
