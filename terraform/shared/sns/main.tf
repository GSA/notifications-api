###
# Target space/org
###

data "cloudfoundry_org" "org" {
  name = var.cf_org_name
}

data "cloudfoundry_space" "space" {
  org_name = var.cf_org_name
  name     = var.cf_space_name
}

###
# SNS Space
###
resource "cloudfoundry_space" "cf_sns_service_space" {
  allow_ssh                = var.allow_ssh
  delete_recursive_allowed = var.delete_recursive_allowed
  name                     = data.cloudfoundry_space.space.name
  org                      = data.cloudfoundry_org.org.id
}

###
# SES instance
###

data "cloudfoundry_service" "sns" {
  name = "ttsnotify-sms"
}

resource "cloudfoundry_service_instance" "sns" {
  name         = var.name
  space        = data.cloudfoundry_space.space.id
  service_plan = data.cloudfoundry_service.sns.service_plans["base"]
  json_params = jsonencode({
    region              = var.aws_region
    monthly_spend_limit = var.monthly_spend_limit
  })
}
