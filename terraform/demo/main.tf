locals {
  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = "notify-demo"
  env           = "demo"
  app_name      = "notify-api"
}

module "database" {
  source = "github.com/18f/terraform-cloudgov//database?ref=v0.7.1"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  name             = "${local.app_name}-rds-${local.env}"
  recursive_delete = local.recursive_delete
  rds_plan_name    = "micro-psql"
}

module "redis" { # default v6.2; delete after v7.0 resource is bound
  source = "github.com/18f/terraform-cloudgov//redis?ref=v0.7.1"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  name             = "${local.app_name}-redis-${local.env}"
  recursive_delete = local.recursive_delete
  redis_plan_name  = "redis-dev"
}

module "redis-v70" {
  source = "github.com/GSA-TTS/terraform-cloudgov//redis?ref=v1.0.0"

  cf_org_name     = local.cf_org_name
  cf_space_name   = local.cf_space_name
  name            = "${local.app_name}-redis-v70-${local.env}"
  redis_plan_name = "redis-dev"
  json_params = jsonencode(
    {
      "engineVersion" : "7.0",
    }
  )
}

module "csv_upload_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.7.1"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  name             = "${local.app_name}-csv-upload-bucket-${local.env}"
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
