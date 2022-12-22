locals {
  cf_org_name      = "gsa-tts-benefits-studio-prototyping"
  cf_space_name    = "notify-prod"
  env              = "production"
  app_name         = "notify-api"
  recursive_delete = false
}

module "database" {
  source = "github.com/18f/terraform-cloudgov//database?ref=v0.1.0"

  cf_user          = var.cf_user
  cf_password      = var.cf_password
  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  env              = local.env
  app_name         = local.app_name
  recursive_delete = local.recursive_delete
  rds_plan_name    = "TKTK-production-rds-plan"
}

module "redis" {
  source = "github.com/18f/terraform-cloudgov//redis?ref=v0.1.0"

  cf_user          = var.cf_user
  cf_password      = var.cf_password
  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  env              = local.env
  app_name         = local.app_name
  recursive_delete = local.recursive_delete
  redis_plan_name  = "TKTK-production-redis-plan"
}

module "csv_upload_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.1.0"

  cf_user          = var.cf_user
  cf_password      = var.cf_password
  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  s3_service_name  = "${local.app_name}-csv-upload-bucket-${local.env}"
}

module "contact_list_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.1.0"

  cf_user          = var.cf_user
  cf_password      = var.cf_password
  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  s3_service_name  = "${local.app_name}-contact-list-bucket-${local.env}"
}

module "egress-space" {
  source = "../shared/egress_space"

  cf_user                  = var.cf_user
  cf_password              = var.cf_password
  cf_org_name              = local.cf_org_name
  cf_restricted_space_name = local.cf_space_name
  deployers = [
    var.cf_user
  ]
}

###########################################################################
# The following lines need to be commented out for the initial `terraform apply`
# It can be re-enabled after:
# 1) the app has first been deployed
# 2) the route has been manually created by an OrgManager:
#     `cf create-domain TKTK-org-name TKTK-production-domain-name`
###########################################################################
# module "domain" {
#   source = "github.com/18f/terraform-cloudgov//domain?ref=v0.1.0"
#
#   cf_user          = var.cf_user
#   cf_password      = var.cf_password
#   cf_org_name      = local.cf_org_name
#   cf_space_name    = local.cf_space_name
#   env              = local.env
#   app_name         = local.app_name
#   recursive_delete = local.recursive_delete
#   cdn_plan_name    = "domain"
#   domain_name      = "TKTK-production-domain-name"
# }
