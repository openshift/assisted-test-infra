locals {
  master_vnic_ids = concat(flatten(data.oci_core_vnic_attachments.master_vnic_attachments[*].vnic_attachments[0].vnic_id), flatten(data.oci_core_vnic_attachments.master_vnic_attachments[*].vnic_attachments[1].vnic_id))
  worker_vnic_ids = concat(flatten(data.oci_core_vnic_attachments.worker_vnic_attachments[*].vnic_attachments[0].vnic_id), flatten(data.oci_core_vnic_attachments.worker_vnic_attachments[*].vnic_attachments[1].vnic_id))

  vnic_by_vnic_id = {
    for vnic in concat(data.oci_core_vnic.master_all_vnics, data.oci_core_vnic.worker_all_vnics) :
    vnic.id => vnic
  }

  vnic_ids_by_instance_id = {
    for attachment in concat(data.oci_core_vnic_attachments.master_vnic_attachments, data.oci_core_vnic_attachments.worker_vnic_attachments) :
    attachment.instance_id => flatten(attachment.vnic_attachments[*].vnic_id)
  }

  vnics_by_instance_id = {
    for instance_id, vnic_ids in local.vnic_ids_by_instance_id :
    instance_id => [ 
      for vnic_id in vnic_ids : local.vnic_by_vnic_id[vnic_id]
    ]
  }

  nmstate_routes = {
    routes = {
      config = [
        {
          # default interface used by OCP
          destination        = "0.0.0.0/0"
          next-hop-address   = data.oci_core_subnet.private_subnet.virtual_router_ip
          next-hop-interface = "ens4"
        },
        {
          # route to iSCSI block volume
          destination        = "169.254.0.0/16"
          next-hop-address   = "0.0.0.0"
          next-hop-interface = "ens3"
        }
      ]
    }
  }
  nmstate_dns = {
    dns-resolver = {
      config = {
        server = [
          "169.254.169.254"
        ],
        search = [
          data.oci_core_subnet.private_subnet.subnet_domain_name
        ]
      }
    }
  }

  nmstate_mac_interface_map_by_instance_id = {
    for instance_id, vnics in local.vnics_by_instance_id :
    instance_id => {
      mac_interface_map = [
        for vnic in vnics :
        {
          mac_address      = vnic.mac_address,
          logical_nic_name = vnic.is_primary ? "ens3" : "ens4"
        }
      ]
    }
  }

  nmstate_interfaces_by_instance_id = {
    for instance_id, vnics in local.vnics_by_instance_id :
    instance_id => {
      interfaces = [
        for vnic in vnics :
        {
          name  = vnic.is_primary ? "ens3" : "ens4",
          type  = "ethernet",
          state = "up"
          ipv4 = {
            enabled = true
            address = [
              {
                ip            = vnic.private_ip_address,
                prefix-length = reverse(split("/", data.oci_core_subnet.private_subnet.cidr_block))[0]
              }
            ]
          },
          ipv6 = {
            enabled = false
          }
        }
      ]
    }
  }

  nmstate = [
    for instance_id, interfaces in local.nmstate_interfaces_by_instance_id :
    merge(interfaces, local.nmstate_mac_interface_map_by_instance_id[instance_id], local.nmstate_dns, local.nmstate_routes)
  ]
}

data "oci_core_vnic_attachments" "master_vnic_attachments" {
  count = length(oci_core_instance.master)

  compartment_id      = var.oci_compartment_oicd
  availability_domain = oci_core_instance.master[count.index].availability_domain
  instance_id         = oci_core_instance.master[count.index].id

  depends_on = [oci_core_vnic_attachment.master_vnic_attachments]
}

data "oci_core_vnic_attachments" "worker_vnic_attachments" {
  count = length(oci_core_instance.worker)

  compartment_id      = var.oci_compartment_oicd
  availability_domain = oci_core_instance.worker[count.index].availability_domain
  instance_id         = oci_core_instance.worker[count.index].id

  depends_on = [oci_core_vnic_attachment.worker_vnic_attachments]
}
data "oci_core_vnic" "master_all_vnics" {
  count = length(local.master_vnic_ids)

  vnic_id = local.master_vnic_ids[count.index]
}

data "oci_core_vnic" "worker_all_vnics" {
  count = length(local.worker_vnic_ids)

  vnic_id = local.worker_vnic_ids[count.index]
}

data "oci_core_subnet" "private_subnet" {
  subnet_id = var.oci_private_subnet_oicd
}

output "static_ip_config" {
  value = yamlencode(local.nmstate)
}

