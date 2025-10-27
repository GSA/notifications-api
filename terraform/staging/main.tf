locals {
  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = "notify-staging"
  env           = "staging"
  app_name      = "notify-api"
}

resource "null_resource" "prevent_destroy" {

  lifecycle {
    prevent_destroy = false # destroying staging is allowed
  }
}


data "cloudfoundry_space" "space" {
  provider = cloudfoundry.official
  org      = "9e428562-a2d9-41b4-9c23-1ef5237fb44e"
  name     = local.cf_space_name
}

module "database" {
  source = "github.com/GSA-TTS/terraform-cloudgov//database?ref=v1.0.0"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${local.app_name}-rds-${local.env}"
  rds_plan_name = "small-psql"
}


module "redis-v70" {
  source = "github.com/GSA-TTS/terraform-cloudgov//redis?ref=v2.4.0"
  # Right now the default is cfcommunity, remove this when default is cloudfoundry
  providers = {
    cloudfoundry = cloudfoundry.official
  }
  cf_space_id     = data.cloudfoundry_space.space.id
  name            = "${local.app_name}-redis-v70-${local.env}"
  redis_plan_name = "redis-dev"
  json_params = jsonencode(
    {
      "engineVersion" : "7.0",
    }
  )
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
    "carlo.costino@gsa.gov"
  ]
}

module "ses_email" {
  source              = "../shared/ses"
  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-ses-${local.env}"
  aws_region          = "us-west-2"
  mail_from_subdomain = "mail"
  email_receipt_error = "notify-support@gsa.gov"
}

module "sns_sms" {
  source = "../shared/sns"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-sns-${local.env}"
  aws_region          = "us-west-2"
  monthly_spend_limit = 25
}
