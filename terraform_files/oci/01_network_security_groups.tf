# Create security groups for the future cluster
# LB should be able to reach:
#   - cluster nodes
# cluster nodes should be able to reach:
#   - LB (internal and external)
#   - Other cluster nodes

# load-balancer is hold by LB
resource "oci_core_network_security_group" "nsg_load_balancer" {
  #Required
  compartment_id = var.oci_compartment_oicd
  vcn_id         = var.oci_vcn_oicd

  #Optional
  display_name = "${var.cluster_name}-load-balancer"
}

# load-balancer-access is hold by cluster nodes and CI machine
resource "oci_core_network_security_group" "nsg_load_balancer_access" {
  #Required
  compartment_id = var.oci_compartment_oicd
  vcn_id         = var.oci_vcn_oicd

  #Optional
  display_name = "${var.cluster_name}-load-balancer-access"
}

# all instances holding load-balancer-access NSG can reach load-balancer
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_load_balancer_access" {
  network_security_group_id = oci_core_network_security_group.nsg_load_balancer.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_load_balancer_access.id
  protocol                  = "all"
}

# cluster NSG is hold by all clusters nodes
resource "oci_core_network_security_group" "nsg_cluster" {
  #Required
  compartment_id = var.oci_compartment_oicd
  vcn_id         = var.oci_vcn_oicd

  #Optional
  display_name = "${var.cluster_name}-cluster"
}

# cluster-access is hold by LB and CI machine
resource "oci_core_network_security_group" "nsg_cluster_access" {
  #Required
  compartment_id = var.oci_compartment_oicd
  vcn_id         = var.oci_vcn_oicd

  #Optional
  display_name = "${var.cluster_name}-cluster-access"
}

# all instances holding cluster-access NSG can reach cluster
resource "oci_core_network_security_group_security_rule" "rule_allow_from_nsg_cluster_access" {
  network_security_group_id = oci_core_network_security_group.nsg_cluster.id
  direction                 = "INGRESS"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.nsg_cluster_access.id
  protocol                  = "all"
}
