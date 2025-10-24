###
# Target space/org
###

data "cloudfoundry_space" "space" {
  org_name = var.cf_org_name
  name     = var.cf_space_name
}

###
# SES instance
###

data "cloudfoundry_service" "ses" {
  name = "datagov-smtp"
}

# resource "cloudfoundry_service_instance" "ses_community" {
#  name         = var.name
#  space        = data.cloudfoundry_space.space.id
#  service_plan = data.cloudfoundry_service.ses.service_plans["base"]
#  json_params = jsonencode({
#    region                        = var.aws_region
#    domain                        = var.email_domain
#    mail_from_subdomain           = var.mail_from_subdomain
#    email_receipt_error           = var.email_receipt_error
#    enable_feedback_notifications = true
#  })
#}

resource "cloudfoundry_service_instance" "ses" {
  providers = {
    cloudfoundry = cloudfoundry.official
  }
  name         = var.name
  space        = data.cloudfoundry_space.space.id
  service_plan = data.cloudfoundry_service.ses.service_plans["base"]
  json_params = jsonencode({
    region                        = var.aws_region
    domain                        = var.email_domain
    mail_from_subdomain           = var.mail_from_subdomain
    email_receipt_error           = var.email_receipt_error
    enable_feedback_notifications = true
  })
}
