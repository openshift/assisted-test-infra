data "oci_identity_availability_domains" "ads" {
  compartment_id = var.oci_compartment_id
}

locals {
  availability_domains       = data.oci_identity_availability_domains.ads.availability_domains
  availability_domains_count = length(data.oci_identity_availability_domains.ads.availability_domains)
}

# Create master instances
resource "oci_core_instance" "masters" {
  count = var.masters_count

  # Required
  availability_domain = local.availability_domains[count.index % local.availability_domains_count].name
  compartment_id      = var.oci_compartment_id
  shape               = "VM.Standard.E4.Flex"

  shape_config {
    memory_in_gbs = var.master_instance_memory_gb
    ocpus         = var.master_instance_cpu_count
  }

  source_details {
    source_id               = oci_core_image.discovery_image.id
    source_type             = "image"
    boot_volume_size_in_gbs = 50
  }

  # Optional
  display_name = "${var.cluster_name}-master-${count.index}"

  create_vnic_details {
    assign_public_ip          = false
    assign_private_dns_record = true
    hostname_label            = "${var.cluster_name}-master-${count.index}"
    subnet_id                 = var.oci_private_subnet_id
    nsg_ids = concat(
      [
        oci_core_network_security_group.nsg_cluster.id,
        oci_core_network_security_group.nsg_load_balancer_access.id # allow access to load balancer (api-int)
      ],
      var.oci_extra_node_nsg_ids # e.g.: allow access to ci-machine (assisted-service)
    )
  }

  preserve_boot_volume = false
}

# Create worker instances
resource "oci_core_instance" "workers" {
  count = var.workers_count

  # Required
  availability_domain = local.availability_domains[count.index % local.availability_domains_count].name
  compartment_id      = var.oci_compartment_id
  shape               = "VM.Standard.E4.Flex"

  shape_config {
    memory_in_gbs = var.worker_instance_memory_gb
    ocpus         = var.worker_instance_cpu_count
  }

  source_details {
    source_id               = oci_core_image.discovery_image.id
    source_type             = "image"
    boot_volume_size_in_gbs = 50
  }

  # Optional
  display_name = "${var.cluster_name}-worker-${count.index}"

  create_vnic_details {
    assign_public_ip          = false
    assign_private_dns_record = true
    hostname_label            = "${var.cluster_name}-worker-${count.index}"
    subnet_id                 = var.oci_private_subnet_id
    nsg_ids = concat(
      [
        oci_core_network_security_group.nsg_cluster.id,
        oci_core_network_security_group.nsg_load_balancer_access.id # allow access to load balancer (api-int)
      ],
      var.oci_extra_node_nsg_ids # e.g.: allow access to ci-machine (assisted-service)
    )
  }

  preserve_boot_volume = false
}

