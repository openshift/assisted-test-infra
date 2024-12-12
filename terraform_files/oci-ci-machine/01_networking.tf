locals {
  all_protocols = "all"
  anywhere      = "0.0.0.0/0"
}

resource "oci_core_vcn" "ci_machine_vcn" {
  cidr_blocks = [
    "10.0.0.0/16",
  ]
  compartment_id = var.oci_compartment_id
  display_name   = "vcn-ci-${var.unique_id}"
  dns_label      = "v${substr(var.unique_id, -14, -1)}" # dns label is limited to 15 chacracters
}

resource "oci_core_internet_gateway" "internet_gateway" {
  compartment_id = var.oci_compartment_id
  display_name   = "InternetGateway"
  vcn_id         = oci_core_vcn.ci_machine_vcn.id
}

resource "oci_core_route_table" "public_routes" {
  compartment_id = var.oci_compartment_id
  vcn_id         = oci_core_vcn.ci_machine_vcn.id
  display_name   = "public"

  route_rules {
    destination       = local.anywhere
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.internet_gateway.id
  }
}

resource "oci_core_security_list" "public" {
  compartment_id = var.oci_compartment_id
  display_name   = "public"
  vcn_id         = oci_core_vcn.ci_machine_vcn.id

  ingress_security_rules {
    source   = local.anywhere
    protocol = "6"
    tcp_options {
      min = 22
      max = 22
    }
  }
  ingress_security_rules {
    source   = local.anywhere
    protocol = "6"
    tcp_options {
      min = 8080
      max = 8080
    }
  }
  ingress_security_rules {
    source   = local.anywhere
    protocol = "6"
    tcp_options {
      min = 8090
      max = 8090
    }
  }
  egress_security_rules {
    destination = local.anywhere
    protocol    = local.all_protocols
  }
}

resource "oci_core_subnet" "public" {
  cidr_block     = "10.0.0.0/24"
  display_name   = "public"
  compartment_id = var.oci_compartment_id
  vcn_id         = oci_core_vcn.ci_machine_vcn.id
  route_table_id = oci_core_route_table.public_routes.id

  security_list_ids = [
    oci_core_security_list.public.id,
  ]

  dns_label                  = "public"
  prohibit_public_ip_on_vnic = false
}

