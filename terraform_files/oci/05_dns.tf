locals {
  cluster_ingress_domain = "*.apps.${var.cluster_name}.${var.base_dns_domain}"
  cluster_api_domain     = "api.${var.cluster_name}.${var.base_dns_domain}"
  cluster_api_int_domain = "api-int.${var.cluster_name}.${var.base_dns_domain}"
}

resource "oci_dns_rrset" "dns_rrset_ingress" {
  #Required
  zone_name_or_id = var.base_dns_domain
  domain          = local.cluster_ingress_domain
  rtype           = "A"

  items {
    domain = local.cluster_ingress_domain
    rdata  = local.cluster_nlb_public_ip
    rtype  = "A"
    ttl    = 300
  }
}


resource "oci_dns_rrset" "dns_rrset_api" {
  #Required
  zone_name_or_id = var.base_dns_domain
  domain          = local.cluster_api_domain
  rtype           = "A"

  items {
    domain = local.cluster_api_domain
    rdata  = local.cluster_nlb_public_ip
    rtype  = "A"
    ttl    = 300
  }
}

resource "oci_dns_rrset" "dns_rrset_api_int" {
  #Required
  zone_name_or_id = var.base_dns_domain
  domain          = local.cluster_api_int_domain
  rtype           = "A"

  items {
    domain = local.cluster_api_int_domain
    rdata  = local.cluster_nlb_private_ip
    rtype  = "A"
    ttl    = 300
  }
}
