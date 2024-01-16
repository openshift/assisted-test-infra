# /!\ Ensure all resources are created sequentialy /!\
# Conccurent updates on the same LB create conflicts and make `terraform apply`
# fail

resource "oci_network_load_balancer_network_load_balancer" "nlb" {
  compartment_id = var.oci_compartment_oicd
  subnet_id      = var.oci_public_subnet_oicd

  display_name                   = "nlb-${var.cluster_name}"
  is_preserve_source_destination = false
  is_private                     = false
  network_security_group_ids = concat(
    [
      oci_core_network_security_group.nsg_load_balancer.id,
      oci_core_network_security_group.nsg_cluster_access.id # allow access to cluster (forwarded traffic)
    ],
    var.oci_extra_lb_nsg_oicds # e.g.: allow access to ci-machine to reach the API endpoint
  )
}

locals {
  cluster_nlb_public_ip  = one([for ip in oci_network_load_balancer_network_load_balancer.nlb.ip_addresses : ip.ip_address if ip.is_public])
  cluster_nlb_private_ip = one([for ip in oci_network_load_balancer_network_load_balancer.nlb.ip_addresses : ip.ip_address if !ip.is_public])

  master_private_ips = [for vnic in data.oci_core_vnic.master_secondary_vnics : vnic.private_ip_address]
  worker_private_ips = [for vnic in data.oci_core_vnic.worker_secondary_vnics : vnic.private_ip_address]
}

# Backendset definitions

resource "oci_network_load_balancer_network_load_balancers_backend_sets_unified" "nlb-bes-api" {
  name                     = "bes-api"
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  policy                   = "FIVE_TUPLE"
  is_preserve_source       = false

  health_checker {
    port        = 6443
    protocol    = "HTTPS"
    url_path    = "/readyz"
    return_code = 200
  }

  dynamic "backends" {
    for_each = toset(local.master_private_ips)
    content {
      port       = 6443
      ip_address = backends.value
    }
  }

  depends_on = [
    oci_network_load_balancer_network_load_balancer.nlb
  ]
}

resource "oci_network_load_balancer_network_load_balancers_backend_sets_unified" "nlb-bes-mcs" {
  name                     = "bes-mcs"
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  policy                   = "FIVE_TUPLE"
  is_preserve_source       = false

  health_checker {
    port        = 22623
    protocol    = "HTTPS"
    url_path    = "/healthz"
    return_code = 200
  }

  dynamic "backends" {
    for_each = toset(local.master_private_ips)
    content {
      port       = 22623
      ip_address = backends.key
    }
  }

  depends_on = [
    oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-api
  ]
}

resource "oci_network_load_balancer_network_load_balancers_backend_sets_unified" "nlb-bes-https" {
  name                     = "bes-https"
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  policy                   = "FIVE_TUPLE"
  is_preserve_source       = false

  health_checker {
    port     = 443
    protocol = "TCP"
  }

  dynamic "backends" {
    # for SNO and compact clusters, attach the masters to the HTTPS backend
    for_each = toset(var.workers_count > 0 ? local.worker_private_ips : local.master_private_ips)
    content {
      port       = 443
      ip_address = backends.key
    }
  }

  depends_on = [
    oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-mcs
  ]
}

resource "oci_network_load_balancer_network_load_balancers_backend_sets_unified" "nlb-bes-http" {
  name                     = "bes-http"
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  policy                   = "FIVE_TUPLE"
  is_preserve_source       = false

  health_checker {
    port     = 80
    protocol = "TCP"
  }

  dynamic "backends" {
    # for SNO and compact clusters, attach the masters to the HTTP backend
    for_each = toset(var.workers_count > 0 ? local.worker_private_ips : local.master_private_ips)
    content {
      port       = 80
      ip_address = backends.key
    }
  }

  depends_on = [
    oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-https
  ]
}

# Listener definitions

resource "oci_network_load_balancer_listener" "nlb-listener-api" {
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  name                     = "listener-api"
  default_backend_set_name = oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-api.name
  port                     = 6443
  protocol                 = "TCP"

  depends_on = [
    oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-http
  ]
}

resource "oci_network_load_balancer_listener" "nlb-listener-mcs" {
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  name                     = "listener-mcs"
  default_backend_set_name = oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-mcs.name
  port                     = 22623
  protocol                 = "TCP"

  depends_on = [
    oci_network_load_balancer_listener.nlb-listener-api
  ]
}

resource "oci_network_load_balancer_listener" "nlb-listener-https" {
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  name                     = "listener-https"
  default_backend_set_name = oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-https.name
  port                     = 443
  protocol                 = "TCP"

  depends_on = [
    oci_network_load_balancer_listener.nlb-listener-mcs
  ]
}

resource "oci_network_load_balancer_listener" "nlb-listener-http" {
  network_load_balancer_id = oci_network_load_balancer_network_load_balancer.nlb.id
  name                     = "listener-http"
  default_backend_set_name = oci_network_load_balancer_network_load_balancers_backend_sets_unified.nlb-bes-http.name
  port                     = 80
  protocol                 = "TCP"

  depends_on = [
    oci_network_load_balancer_listener.nlb-listener-https
  ]
}
