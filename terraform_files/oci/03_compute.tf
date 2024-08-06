data "oci_identity_availability_domains" "ads" {
  compartment_id = var.oci_compartment_oicd
}

locals {
  availability_domains       = data.oci_identity_availability_domains.ads.availability_domains
  availability_domains_count = length(data.oci_identity_availability_domains.ads.availability_domains)
}

# Define tag namespace. Use to mark instance roles and configure instance policy
resource "oci_identity_tag_namespace" "cluster_tags" {
  compartment_id = var.oci_compartment_oicd
  description    = "Used for track ${var.cluster_name} related resources and policies"
  is_retired     = "false"
  name           = var.cluster_name
}

resource "oci_identity_tag" "cluster_instance_role" {
  description      = "Describe instance role inside OpenShift cluster"
  is_cost_tracking = "false"
  is_retired       = "false"
  name             = "instance-role"
  tag_namespace_id = oci_identity_tag_namespace.cluster_tags.id
  validator {
    validator_type = "ENUM"
    values = [
      "master",
      "worker",
    ]
  }
}

# Create master instances
resource "oci_core_instance" "master" {
  count = var.masters_count

  # Required
  availability_domain = local.availability_domains[count.index % local.availability_domains_count].name
  compartment_id      = var.oci_compartment_oicd
  shape               = var.instance_shape

  shape_config {
    memory_in_gbs = var.master_memory_gib
    ocpus         = var.master_vcpu
  }

  platform_config {
    type                             = var.instance_platform_config_type
    are_virtual_instructions_enabled = var.instance_platform_config_virtualization_enabled
  }

  source_details {
    source_id               = oci_core_image.discovery_image.id
    source_type             = "image"
    boot_volume_size_in_gbs = var.master_disk_size_gib
    boot_volume_vpus_per_gb = 20
  }

  # Optional
  display_name = "${var.cluster_name}-master-${count.index}"

  create_vnic_details {
    assign_public_ip          = false
    assign_private_dns_record = true
    hostname_label            = "${var.cluster_name}-master-${count.index}"
    subnet_id                 = var.oci_boot_volume_type != null && var.oci_boot_volume_type == "ISCSI" ? var.oci_iscsi_subnet_oicd : var.oci_private_subnet_oicd
    nsg_ids = concat(
      [
        oci_core_network_security_group.nsg_cluster.id,
        oci_core_network_security_group.nsg_cluster_access.id,      # allow access from other cluster nodes
        oci_core_network_security_group.nsg_load_balancer_access.id # allow access from load balancer
      ],
      var.oci_extra_node_nsg_oicds # e.g.: allow access to ci-machine (assisted-service)
    )
  }

  defined_tags = {
    "${var.cluster_name}.instance-role" = "master"
  }

  preserve_boot_volume = false

  # ensure the custom image was updated before creating these instances
  depends_on = [oci_core_compute_image_capability_schema.discovery_image_firmware_uefi_64]
}

resource "oci_core_vnic_attachment" "master_vnic_attachment" {
  count = var.oci_boot_volume_type != null && var.oci_boot_volume_type == "ISCSI" ? var.masters_count : 0
  create_vnic_details {
    assign_public_ip          = false
    assign_private_dns_record = true
    hostname_label            = "${var.cluster_name}-master-ocp-${count.index}"
    subnet_id                 = var.oci_private_subnet_oicd
    nsg_ids = concat(
      [
        oci_core_network_security_group.nsg_cluster.id,
        oci_core_network_security_group.nsg_cluster_access.id,      # allow access from other cluster nodes
        oci_core_network_security_group.nsg_load_balancer_access.id # allow access from load balancer
      ],
      var.oci_extra_node_nsg_oicds # e.g.: allow access to ci-machine (assisted-service)
    )
  }
  instance_id  = oci_core_instance.master[count.index]
  display_name = "${var.cluster_name}-master-vnic-ocp"
}

# Create worker instances
resource "oci_core_instance" "worker" {
  count = var.workers_count

  # Required
  availability_domain = local.availability_domains[count.index % local.availability_domains_count].name
  compartment_id      = var.oci_compartment_oicd
  shape               = var.instance_shape

  shape_config {
    memory_in_gbs = var.worker_memory_gib
    ocpus         = var.worker_vcpu
  }

  platform_config {
    type                             = var.instance_platform_config_type
    are_virtual_instructions_enabled = var.instance_platform_config_virtualization_enabled
  }

  source_details {
    source_id               = oci_core_image.discovery_image.id
    source_type             = "image"
    boot_volume_size_in_gbs = var.worker_disk_size_gib
    boot_volume_vpus_per_gb = 20
  }

  # Optional
  display_name = "${var.cluster_name}-worker-${count.index}"

  create_vnic_details {
    assign_public_ip          = false
    assign_private_dns_record = true
    hostname_label            = "${var.cluster_name}-worker-${count.index}"
    subnet_id                 = var.oci_boot_volume_type != null && var.oci_boot_volume_type == "ISCSI" ? var.oci_iscsi_subnet_oicd : var.oci_private_subnet_oicd
    nsg_ids = concat(
      [
        oci_core_network_security_group.nsg_cluster.id,
        oci_core_network_security_group.nsg_cluster_access.id,      # allow access from other cluster nodes
        oci_core_network_security_group.nsg_load_balancer_access.id # allow access from load balancer
      ],
      var.oci_extra_node_nsg_oicds # e.g.: allow access to ci-machine (assisted-service)
    )
  }

  defined_tags = {
    "${var.cluster_name}.instance-role" = "worker"
  }

  preserve_boot_volume = false

  # ensure the custom image was updated before creating these instances
  depends_on = [oci_core_compute_image_capability_schema.discovery_image_firmware_uefi_64]
}

resource "oci_core_vnic_attachment" "worker_vnic_attachment" {
  count = var.oci_boot_volume_type != null && var.oci_boot_volume_type == "ISCSI" ? var.workers_count : 0
  create_vnic_details {
    assign_public_ip          = false
    assign_private_dns_record = true
    hostname_label            = "${var.cluster_name}-worker-ocp-${count.index}"
    subnet_id                 = var.oci_private_subnet_oicd
    nsg_ids = concat(
      [
        oci_core_network_security_group.nsg_cluster.id,
        oci_core_network_security_group.nsg_cluster_access.id,      # allow access from other cluster nodes
        oci_core_network_security_group.nsg_load_balancer_access.id # allow access from load balancer
      ],
      var.oci_extra_node_nsg_oicds # e.g.: allow access to ci-machine (assisted-service)
    )
  }
  instance_id  = oci_core_instance.worker[count.index]
  display_name = "${var.cluster_name}-worker-vnic-ocp"
}
resource "oci_identity_dynamic_group" "master_nodes" {
  compartment_id = var.oci_tenancy_oicd # dynamic groups can only be created in root compartment
  description    = "${var.cluster_name} master nodes"
  matching_rule  = "all {instance.compartment.id='${var.oci_compartment_oicd}', tag.${var.cluster_name}.instance-role.value='master'}"
  name           = "${var.cluster_name}-masters"
}

# The CCM will run only master nodes, no need to set a policy on worker nodes
resource "oci_identity_policy" "master_nodes" {
  compartment_id = var.oci_compartment_oicd
  description    = "${var.cluster_name} master nodes instance principal"
  name           = "${var.cluster_name}-masters"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.master_nodes.name} to manage volume-family in compartment id ${var.oci_compartment_oicd}",
    "Allow dynamic-group ${oci_identity_dynamic_group.master_nodes.name} to manage instance-family in compartment id ${var.oci_compartment_oicd}",
    "Allow dynamic-group ${oci_identity_dynamic_group.master_nodes.name} to manage security-lists in compartment id ${var.oci_compartment_oicd}",
    "Allow dynamic-group ${oci_identity_dynamic_group.master_nodes.name} to use virtual-network-family in compartment id ${var.oci_compartment_oicd}",
    "Allow dynamic-group ${oci_identity_dynamic_group.master_nodes.name} to manage load-balancers in compartment id ${var.oci_compartment_oicd}",
  ]
}
