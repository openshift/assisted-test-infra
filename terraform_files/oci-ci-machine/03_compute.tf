data "oci_identity_availability_domains" "ads" {
  compartment_id = var.oci_compartment_id
}

# Fetch Rocky Linux 9.x OS image from OCI marketpalce
# See https://blogs.oracle.com/cloud-infrastructure/post/using-terraform-for-marketplace-images
data "oci_marketplace_listings" "os_listings" {
  category       = ["Operating Systems"]
  pricing        = ["FREE"]
  package_type   = "IMAGE"
  compartment_id = var.oci_compartment_id
  filter {
    name   = "name"
    values = ["Rocky Linux 9\\.\\d+ - Free \\(x86_64\\)"]
    regex  = true
  }
}

data "oci_marketplace_listing" "os_listing" {
  listing_id     = data.oci_marketplace_listings.os_listings.listings[0].id
  compartment_id = var.oci_compartment_id
}

data "oci_marketplace_listing_package" "os_listing_package" {
  listing_id      = data.oci_marketplace_listing.os_listing.id
  package_version = data.oci_marketplace_listing.os_listing.default_package_version
  compartment_id  = var.oci_compartment_id
}

data "oci_core_app_catalog_listing_resource_version" "os_catalog_listing" {
  listing_id       = data.oci_marketplace_listing_package.os_listing_package.app_catalog_listing_id
  resource_version = data.oci_marketplace_listing_package.os_listing_package.app_catalog_listing_resource_version
}

data "oci_marketplace_listing_package_agreements" "os_listing_package_agreements" {
  listing_id      = data.oci_marketplace_listing.os_listing.id
  package_version = data.oci_marketplace_listing.os_listing.default_package_version
  compartment_id  = var.oci_compartment_id
}

# Sign agreement to use Rocky Linux from the OCI marketpalce
resource "oci_marketplace_accepted_agreement" "os_accepted_agreement" {
  agreement_id    = oci_marketplace_listing_package_agreement.os_listing_package_agreement.agreement_id
  compartment_id  = var.oci_compartment_id
  listing_id      = data.oci_marketplace_listing.os_listing.id
  package_version = data.oci_marketplace_listing.os_listing.default_package_version
  signature       = oci_marketplace_listing_package_agreement.os_listing_package_agreement.signature
}
resource "oci_marketplace_listing_package_agreement" "os_listing_package_agreement" {
  agreement_id    = data.oci_marketplace_listing_package_agreements.os_listing_package_agreements.agreements[0].id
  listing_id      = data.oci_marketplace_listing.os_listing.id
  package_version = data.oci_marketplace_listing.os_listing.default_package_version
}

# Use cloud init to configure root user
data "cloudinit_config" "config" {
  part {
    content_type = "text/cloud-config"

    content = yamlencode({
      "users" : [
        {
          "name" : "root",
          "ssh-authorized-keys" : [
            file(var.public_ssh_key_path)
          ]
        }
      ]
    })
  }
}

resource "oci_core_instance" "ci_instance" {
  # Required
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.oci_compartment_id
  shape               = "VM.Standard3.Flex"

  shape_config {
    memory_in_gbs = 16
    ocpus         = 4
  }

  platform_config {
    type                             = "INTEL_VM"
    are_virtual_instructions_enabled = true
  }

  source_details {
    source_id               = data.oci_core_app_catalog_listing_resource_version.os_catalog_listing.listing_resource_id
    source_type             = "image"
    boot_volume_size_in_gbs = 500
    boot_volume_vpus_per_gb = 30
  }

  # Optional
  display_name = "ci-instance-${var.unique_id}"

  create_vnic_details {
    assign_public_ip          = true
    assign_private_dns_record = true
    hostname_label            = "ci-instance"
    subnet_id                 = oci_core_subnet.vcn_public_subnet.id
    nsg_ids = [
      oci_core_network_security_group.nsg_ci_machine.id,
      oci_core_network_security_group.nsg_load_balancer_ci_access.id, # allow access to load balancer
      oci_core_network_security_group.nsg_cluster_ci_access.id        # allow access to cluster (SSH)
    ]
  }
  metadata = {
    user_data = data.cloudinit_config.config.rendered
  }
  preserve_boot_volume = false

  # wait an ssh connection and wait for cloud-init to complete
  connection {
    type        = "ssh"
    user        = "root"
    host        = self.public_ip
    timeout     = "5m"
    private_key = file(var.private_ssh_key_path)
  }

  provisioner "remote-exec" {
    inline = [
      # Wait for cloud-init to complete.
      "cloud-init status --wait || true"
    ]
  }
  lifecycle {
    ignore_changes = [
      source_details[0].source_id,
    ]
  }
}
