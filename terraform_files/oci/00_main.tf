terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "4.117.0"
    }
  }
}

provider "oci" {
}

# Retrieve VCN and subnets linked for this CI job
# The VCN is created when the CI machine is created
data "oci_core_vcns" "job_vcns" {
  #Required
  compartment_id = var.parent_compartment_ocid
  #Optional
  display_name = "vcn-ci-${var.unique_id}"
}

locals {
  vcn_id = one(data.oci_core_vcns.job_vcns.virtual_networks[*].id)
}

data "oci_core_subnets" "job_subnets" {
  #Required
  compartment_id = var.parent_compartment_ocid
  #Optional
  vcn_id = local.vcn_id
}

locals {
  private_subnet_id = one([for s in data.oci_core_subnets.job_subnets.subnets : s.id if s.display_name == "private-subnet"])
  public_subnet_id  = one([for s in data.oci_core_subnets.job_subnets.subnets : s.id if s.display_name == "public-subnet"])
}

#Retrieve NSGs created during CI machine setup
data "oci_core_network_security_groups" "job_nsgs" {
  vcn_id         = local.vcn_id
  compartment_id = var.parent_compartment_ocid
}

locals {
  nsg_load_balancer_id = one([
    for n in data.oci_core_network_security_groups.job_nsgs.network_security_groups : n.id if n.display_name == "load-balancer"
  ])
  nsg_load_balancer_access_id = one([
    for n in data.oci_core_network_security_groups.job_nsgs.network_security_groups : n.id if n.display_name == "load-balancer-access"
  ])
  nsg_cluster_id = one([
    for n in data.oci_core_network_security_groups.job_nsgs.network_security_groups : n.id if n.display_name == "cluster"
  ])
  nsg_cluster_access_id = one([
    for n in data.oci_core_network_security_groups.job_nsgs.network_security_groups : n.id if n.display_name == "cluster-access"
  ])
  nsg_ci_machine_access_id = one([
    for n in data.oci_core_network_security_groups.job_nsgs.network_security_groups : n.id if n.display_name == "ci-machine-access"
  ])
}
