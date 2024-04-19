locals {
  cf_org_name     = "gsa-tts-benefits-studio"
  cf_space_name   = "notify-management"
  s3_service_name = "notify-terraform-state"
}

data "cloudfoundry_org" "org" {
  name = local.cf_org_name
}

resource "cloudfoundry_space" "notify-management" {
  delete_recursive_allowed = false
  name                     = local.cf_space_name
  org                      = data.cloudfoundry_org.org.id
  asgs                     = [
    "71d5aa70-fdce-46fa-8494-aabdb8cae381", # trusted_local_networks_egress
    "c70d6061-4da3-4cbb-bd8e-c9982a5e8b22", # public_networks_egress
    # Public egress is needed for service brokers's Terraform to reach AWS APIs
  ]
  lifecycle {
    # Never delete the bucket that holds Terraform state nor the other
    # important contents of the notify-management space
    prevent_destroy = true
  }
}

module "s3" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.7.1"

  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = local.cf_space_name
  name          = local.s3_service_name
}

resource "cloudfoundry_service_key" "bucket_creds" {
  name             = "${local.s3_service_name}-access"
  service_instance = module.s3.bucket_id
}
