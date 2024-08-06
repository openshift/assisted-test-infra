module "vcn" {
  source  = "oracle-terraform-modules/vcn/oci"
  version = "3.5.4"
  # insert the 5 required variables here

  # Required Inputs
  compartment_id = var.oci_compartment_id

  internet_gateway_route_rules = null
  local_peering_gateways       = null
  nat_gateway_route_rules      = null

  # Optional Inputs
  vcn_name      = "vcn-ci-${var.unique_id}"
  vcn_dns_label = "v${substr(var.unique_id, -14, -1)}" # dns label is limited to 15 chacracters
  vcn_cidrs     = ["10.0.0.0/16"]

  create_internet_gateway = true
  create_nat_gateway      = true
}

resource "oci_core_security_list" "private_security_list" {

  # Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  # Optional
  display_name = "security-list-for-private-subnet"

  egress_security_rules {
    stateless        = false
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "all"
  }

  ingress_security_rules {
    stateless   = false
    source      = "10.0.0.0/16"
    source_type = "CIDR_BLOCK"
    # Get protocol numbers from https://www.iana.org/assignments/protocol-numbers/protocol-numbers.xhtml TCP is 6
    protocol = "6"
    tcp_options {
      min = 22
      max = 22
    }
  }
  ingress_security_rules {
    stateless   = false
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    # Get protocol numbers from https://www.iana.org/assignments/protocol-numbers/protocol-numbers.xhtml ICMP is 1
    protocol = "1"

    # For ICMP type and code see: https://www.iana.org/assignments/icmp-parameters/icmp-parameters.xhtml
    icmp_options {
      type = 3
      code = 4
    }
  }
  ingress_security_rules {
    stateless   = false
    source      = "10.0.0.0/16"
    source_type = "CIDR_BLOCK"
    # Get protocol numbers from https://www.iana.org/assignments/protocol-numbers/protocol-numbers.xhtml ICMP is 1
    protocol = "1"

    # For ICMP type and code see: https://www.iana.org/assignments/icmp-parameters/icmp-parameters.xhtml
    icmp_options {
      type = 3
    }
  }
}

resource "oci_core_security_list" "public_security_list" {

  # Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id

  # Optional
  display_name = "security-list-for-public-subnet"

  egress_security_rules {
    stateless        = false
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "all"
  }

  ingress_security_rules {
    stateless   = false
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    # Get protocol numbers from https://www.iana.org/assignments/protocol-numbers/protocol-numbers.xhtml TCP is 6
    protocol = "6"
    tcp_options {
      min = 22
      max = 22
    }
  }
  ingress_security_rules {
    stateless   = false
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    # Get protocol numbers from https://www.iana.org/assignments/protocol-numbers/protocol-numbers.xhtml ICMP is 1
    protocol = "1"

    # For ICMP type and code see: https://www.iana.org/assignments/icmp-parameters/icmp-parameters.xhtml
    icmp_options {
      type = 3
      code = 4
    }
  }
  ingress_security_rules {
    stateless   = false
    source      = "10.0.0.0/16"
    source_type = "CIDR_BLOCK"
    # Get protocol numbers from https://www.iana.org/assignments/protocol-numbers/protocol-numbers.xhtml ICMP is 1
    protocol = "1"

    # For ICMP type and code see: https://www.iana.org/assignments/icmp-parameters/icmp-parameters.xhtml
    icmp_options {
      type = 3
    }
  }
}

resource "oci_core_subnet" "vcn_private_subnet" {

  # Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id
  cidr_block     = "10.0.1.0/24"
  dns_label      = "private"

  # Optional
  # Caution: For the route table id, use module.vcn.nat_route_id.
  # Do not use module.vcn.nat_gateway_id, because it is the OCID for the gateway and not the route table.
  route_table_id    = module.vcn.nat_route_id
  security_list_ids = [oci_core_security_list.private_security_list.id]
  display_name      = "private-subnet"
}

resource "oci_core_subnet" "vcn_public_subnet" {

  # Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id
  cidr_block     = "10.0.0.0/24"
  dns_label      = "public"

  # Optional
  route_table_id    = module.vcn.ig_route_id
  security_list_ids = [oci_core_security_list.public_security_list.id]
  display_name      = "public-subnet"
}

resource "oci_core_subnet" "vcn_iscsi_subnet" {

  # Required
  compartment_id = var.oci_compartment_id
  vcn_id         = module.vcn.vcn_id
  cidr_block     = "10.0.2.0/24"
  dns_label      = "iscsi"

  # Optional
  # Caution: For the route table id, use module.vcn.nat_route_id.
  # Do not use module.vcn.nat_gateway_id, because it is the OCID for the gateway and not the route table.
  route_table_id    = module.vcn.nat_route_id
  security_list_ids = [oci_core_security_list.private_security_list.id]
  display_name      = "iscsi-subnet"
}
