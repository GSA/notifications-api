locals {
  cf_org_name      = "gsa-tts-benefits-studio"
  cf_space_name    = "notify-demo"
  env              = "demo"
  app_name         = "notify-api"
  recursive_delete = false # deprecated, still used in shared modules
}


resource "null_resource" "prevent_destroy" {

  lifecycle {
    prevent_destroy = true
  }
}

module "database" {
  source = "github.com/GSA-TTS/terraform-cloudgov//database?ref=v1.0.0"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${local.app_name}-rds-${local.env}"
  rds_plan_name = "micro-psql"
}

module "redis" {
  source = "github.com/GSA-TTS/terraform-cloudgov//redis?ref=v1.0.0"

  cf_org_name     = local.cf_org_name
  cf_space_name   = local.cf_space_name
  name            = "${local.app_name}-redis-${local.env}"
  redis_plan_name = "redis-dev"
}

module "csv_upload_bucket" {
  source = "github.com/GSA-TTS/terraform-cloudgov//s3?ref=v1.0.0"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${local.app_name}-csv-upload-bucket-${local.env}"
}

module "egress-space" {
  source = "../shared/egress_space"

  cf_org_name              = local.cf_org_name
  cf_restricted_space_name = local.cf_space_name
  deployers = [
    var.cf_user,
    "steven.reilly@gsa.gov"
  ]
}

module "ses_email" {
  source = "../shared/ses"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-ses-${local.env}"
  aws_region          = "us-west-2"
  email_domain        = "notify.sandbox.10x.gsa.gov"
  email_receipt_error = "notify-support@gsa.gov"
}

module "sns_sms" {
  source = "../shared/sns"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-sns-${local.env}"
  aws_region          = "us-east-1"
  monthly_spend_limit = 25
}
