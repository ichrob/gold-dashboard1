# Inputs must come from the OCI account review before generating a saved plan.
# Use an existing Bob compartment, subnet and reviewed Always Free ARM64 platform image.
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
variable "subnet_id" { type = string }
variable "reviewed_image_id" { type = string }
variable "ssh_public_key" { type = string }
variable "availability_domain" {
  type = string
  validation {
    condition     = can(regex(":EU-ZURICH-1-AD-1$", upper(var.availability_domain)))
    error_message = "Select Zurich AD-1."
  }
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
    source_id               = var.reviewed_image_id
    boot_volume_size_in_gbs = 50
    boot_volume_vpus_per_gb = 10
  }
  create_vnic_details {
    subnet_id        = var.subnet_id
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
  }
}
