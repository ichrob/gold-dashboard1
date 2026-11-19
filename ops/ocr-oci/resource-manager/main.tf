# Inputs must come from the OCI account review before generating a saved plan.
# Use an existing Bob compartment and reviewed Always Free ARM64 platform image.
terraform {
  required_version = ">= 1.2.0"
  required_providers {
    oci = {
      source = "oracle/oci"
    }
  }
}

provider "oci" {
  region = "eu-zurich-1"
}

variable "compartment_id" { type = string }
data "oci_core_images" "bob_ubuntu" {
  compartment_id   = var.compartment_id
  operating_system = "Canonical Ubuntu"
  shape            = "VM.Standard.A1.Flex"
  state            = "AVAILABLE"
}

locals {
  platform_ids = [
    for image in data.oci_core_images.bob_ubuntu.images : image.id
    if coalesce(image.compartment_id, "platform") == "platform" && image.display_name == "Canonical-Ubuntu-24.04-aarch64-2026.11.05-0"
  ]
}
variable "ssh_public_key" { type = string }
variable "availability_domain" {
  type = string
  validation {
    condition     = can(regex(":EU-ZURICH-1-AD-1$", upper(var.availability_domain)))
    error_message = "Select Zurich AD-1."
  }
}

resource "oci_core_vcn" "bob" {
  compartment_id = var.compartment_id
  display_name   = "bob-ocr-test"
  cidr_blocks    = ["10.73.0.0/24"]
}

resource "oci_core_security_list" "isolated" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.bob.id
  display_name   = "bob-ocr-isolated"
}

resource "oci_core_subnet" "test" {
  compartment_id            = var.compartment_id
  vcn_id                    = oci_core_vcn.bob.id
  display_name              = "bob-ocr-private"
  cidr_block                = "10.73.0.0/28"
  prohibit_public_ip_on_vnic = true
  security_list_ids         = [oci_core_security_list.isolated.id]
}

resource "oci_core_instance" "bob" {
  display_name        = "bob-ocr-zurich"
  compartment_id      = var.compartment_id
  availability_domain = var.availability_domain
  shape               = "VM.Standard.A1.Flex"
  shape_config {
    ocpus         = 1
    memory_in_gbs = 4
  }
  source_details {
    source_type             = "image"
    source_id               = one(local.platform_ids)
    boot_volume_size_in_gbs = 50
    boot_volume_vpus_per_gb = 10
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.test.id
    assign_public_ip = false
  }
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = length(local.platform_ids) == 1
      error_message = "Expected exactly one available Zurich Ubuntu ARM64 platform image matching the reviewed build."
    }
  }
}
