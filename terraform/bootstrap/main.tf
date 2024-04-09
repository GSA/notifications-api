locals {
  s3_service_name = "notify-terraform-state"
}

module "s3" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.7.1"

  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = "notify-management"
  name          = local.s3_service_name
}

resource "cloudfoundry_service_key" "bucket_creds" {
  name             = "${local.s3_service_name}-access"
  service_instance = module.s3.bucket_id
}
