locals {
  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = "notify-sandbox"
  env           = "sandbox"
  app_name      = "notify-api"
}

data "cloudfoundry_org" "org" {
  name = local.cf_org_name
}

# This resource imported in imports.tf
resource "cloudfoundry_space" "notify-sandbox" {
  delete_recursive_allowed = true
  name                     = local.cf_space_name
  org                      = data.cloudfoundry_org.org.id
  lifecycle {
    prevent_destroy = false # sandbox is ephemeral; delete and destroy OK
  }
}

module "database" {
  source = "github.com/18f/terraform-cloudgov//database?ref=v0.7.1"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${local.app_name}-rds-${local.env}"
  rds_plan_name = "micro-psql"
}

module "redis" {
  source = "github.com/18f/terraform-cloudgov//redis?ref=v0.7.1"

  cf_org_name     = local.cf_org_name
  cf_space_name   = local.cf_space_name
  name            = "${local.app_name}-redis-${local.env}"
  redis_plan_name = "redis-dev"
}

module "csv_upload_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.7.1"

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
    "steven.reilly@gsa.gov",
    "carlo.costino@gsa.gov"
  ]
}

module "ses_email" {
  source = "../shared/ses"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-ses-${local.env}"
  aws_region          = "us-west-2"
  email_receipt_error = "notify-support@gsa.gov"
}

module "sns_sms" {
  source = "../shared/sns"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-sns-${local.env}"
  aws_region          = "us-east-2"
  monthly_spend_limit = 1
}
