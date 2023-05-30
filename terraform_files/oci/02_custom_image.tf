data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.oci_compartment_id
}

resource "oci_objectstorage_bucket" "discovery_bucket" {
  #Required
  compartment_id = var.oci_compartment_id
  name           = "discovery-${var.cluster_name}"
  namespace      = data.oci_objectstorage_namespace.ns.namespace

  #Optional
  access_type = "NoPublicAccess"
}

resource "oci_objectstorage_object" "discovery_object" {
  #Required
  bucket    = oci_objectstorage_bucket.discovery_bucket.name
  source    = var.discovery_image_path
  namespace = data.oci_objectstorage_namespace.ns.namespace
  object    = basename(var.discovery_image_path)
}

resource "oci_core_image" "discovery_image" {
  #Required
  compartment_id = var.oci_compartment_id

  #Optional
  display_name = oci_objectstorage_object.discovery_object.object
  launch_mode  = "NATIVE" # TODO: change it to PARAVIRTUALIZED but image capability should be updated to set the firmware to UEFI_64

  image_source_details {
    source_type    = "objectStorageTuple"
    bucket_name    = oci_objectstorage_bucket.discovery_bucket.name
    namespace_name = data.oci_objectstorage_namespace.ns.namespace
    object_name    = oci_objectstorage_object.discovery_object.object # exported image name

    #Optional
    source_image_type = "QCOW2"
  }
}
