data "oci_identity_availability_domains" "ads" {
  compartment_id = var.oci_compartment_id
}

data "oci_core_images" "os_images" {
  #Required
  compartment_id = var.oci_compartment_id

  display_name = var.os_image_name
  state        = "AVAILABLE"
  sort_by      = "TIMECREATED"
  sort_order   = "DESC"
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
      }
    )
  }
}

resource "oci_core_instance" "ci_instance" {
  # Required
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.oci_compartment_id
  shape               = "VM.Standard.E4.Flex"

  shape_config {
    memory_in_gbs = 32
    ocpus         = 8
  }

  source_details {
    source_id               = data.oci_core_images.os_images.images[0].id
    source_type             = "image"
    boot_volume_size_in_gbs = 500
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
}
