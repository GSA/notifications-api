###
# Target space/org
###

data "cloudfoundry_space" "space" {
  delete_recursive_allowed = true
  org_name                 = var.cf_org_name
  name                     = var.cf_space_name
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
