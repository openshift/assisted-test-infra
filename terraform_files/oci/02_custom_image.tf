data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.oci_compartment_oicd
}

resource "oci_objectstorage_bucket" "discovery_bucket" {
  #Required
  compartment_id = var.oci_compartment_oicd
  name           = "discovery-${var.cluster_name}"
  namespace      = data.oci_objectstorage_namespace.ns.namespace

  #Optional
  access_type = "NoPublicAccess"
}

resource "oci_objectstorage_object" "discovery_object" {
  #Required
  bucket    = oci_objectstorage_bucket.discovery_bucket.name
  source    = var.iso_download_path
  namespace = data.oci_objectstorage_namespace.ns.namespace
  object    = basename(var.iso_download_path)
}

resource "oci_core_image" "discovery_image" {
  #Required
  compartment_id = var.oci_compartment_oicd

  #Optional
  display_name = oci_objectstorage_object.discovery_object.object
  launch_mode  = "PARAVIRTUALIZED"

  image_source_details {
    source_type    = "objectStorageTuple"
    bucket_name    = oci_objectstorage_bucket.discovery_bucket.name
    namespace_name = data.oci_objectstorage_namespace.ns.namespace
    object_name    = oci_objectstorage_object.discovery_object.object # exported image name

    #Optional
    source_image_type = "QCOW2"
  }
}

#
# Ensure the discovered ISO will boot using UEFI_64
#

locals {
  schema_firmware = {
    "Compute.Firmware" = jsonencode({
      "descriptorType" = "enumstring",
      "source"         = "IMAGE",
      "defaultValue"   = "UEFI_64",
      "values"         = ["UEFI_64"]
    })
  }

  schema_boot_volume_type = var.oci_boot_volume_type == null ? null : {
    "Storage.BootVolumeType" = jsonencode({
      "descriptorType" = "enumstring",
      "source"         = "IMAGE",
      "defaultValue"   = var.oci_boot_volume_type,
      "values"         = [var.oci_boot_volume_type]
    })
  }
}

resource "oci_core_compute_image_capability_schema" "discovery_image_firmware_uefi_64" {
  compartment_id                                      = var.oci_compartment_oicd
  compute_global_image_capability_schema_version_name = data.oci_core_compute_global_image_capability_schemas_versions.global_image_capability_schemas_versions.compute_global_image_capability_schema_versions[0].name
  image_id                                            = oci_core_image.discovery_image.id

  schema_data = merge(local.schema_firmware, local.schema_boot_volume_type)
}

data "oci_core_compute_global_image_capability_schemas_versions" "global_image_capability_schemas_versions" {
  compute_global_image_capability_schema_id = data.oci_core_compute_global_image_capability_schema.global_image_capability_schema.id
}

data "oci_core_compute_global_image_capability_schema" "global_image_capability_schema" {
  compute_global_image_capability_schema_id = data.oci_core_compute_global_image_capability_schemas.global_image_capability_schemas.compute_global_image_capability_schemas[0].id
}

data "oci_core_compute_global_image_capability_schemas" "global_image_capability_schemas" {
}
