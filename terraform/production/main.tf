locals {
  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = "notify-production"
  env           = "production"
  app_name      = "notify-api"
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
  rds_plan_name = "small-psql-redundant"
}

module "redis" { # default v6.2; delete after v7.0 resource is bound
  source = "github.com/GSA-TTS/terraform-cloudgov//redis?ref=v1.0.0"

  cf_org_name     = local.cf_org_name
  cf_space_name   = local.cf_space_name
  name            = "${local.app_name}-redis-${local.env}"
  redis_plan_name = "redis-3node-large"
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
    var.cf_user
  ]
}

module "ses_email" {
  source = "../shared/ses"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-ses-${local.env}"
  aws_region          = "us-gov-west-1"
  email_domain        = "notify.gov"
  mail_from_subdomain = "mail"
  email_receipt_error = "notify-support@gsa.gov"
}

module "sns_sms" {
  source = "../shared/sns"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-sns-${local.env}"
  aws_region          = "us-gov-west-1"
  monthly_spend_limit = 1000
}

###########################################################################
# The following lines need to be commented out for the initial `terraform apply`
# It can be re-enabled after:
# TODO: decide on public API domain name
# 1) the app has first been deployed
# 2) the route has been manually created by an OrgManager:
#     `cf create-domain gsa-tts-benefits-studio api.notify.gov`
###########################################################################
# module "domain" {
#   source = "github.com/18f/terraform-cloudgov//domain?ref=v0.7.1"
#
#   cf_org_name      = local.cf_org_name
#   cf_space_name    = local.cf_space_name
#   app_name_or_id   = "${local.app_name}-${local.env}"
#   name             = "${local.app_name}-domain-${local.env}"
#   recursive_delete = local.recursive_delete
#   cdn_plan_name    = "domain"
#   domain_name      = "api.notify.gov"
# }
