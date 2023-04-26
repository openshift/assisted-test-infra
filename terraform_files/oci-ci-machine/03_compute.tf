data "oci_identity_availability_domains" "ads" {
  compartment_id = var.parent_compartment_ocid
}

data "oci_core_images" "os_images" {
  #Required
  compartment_id = var.parent_compartment_ocid

  operating_system         = "CentOS"
  operating_system_version = "8 Stream"
  state                    = "AVAILABLE"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "ci_instance" {
  # Required
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.parent_compartment_ocid
  shape               = "VM.Standard.E4.Flex"

  shape_config {
    memory_in_gbs = 8
    ocpus         = 2
  }

  source_details {
    source_id               = data.oci_core_images.os_images.images[0].id
    source_type             = "image"
    boot_volume_size_in_gbs = 50
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
      oci_core_network_security_group.nsg_load_balancer_access.id, # allow access to load balancer
      oci_core_network_security_group.nsg_cluster_access.id        # allow access to cluster (SSH)
    ]
  }
  metadata = {
    ssh_authorized_keys = file(var.public_ssh_key_path)
  }
  preserve_boot_volume = false

  # wait an ssh connection and wait for cloud-init to complete
  connection {
    type        = "ssh"
    user        = "opc"
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
