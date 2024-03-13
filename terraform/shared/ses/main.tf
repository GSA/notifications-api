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
# SES Space
###
resource "cloudfoundry_space" "cf_ses_service_space" {
  allow_ssh                = var.allow_ssh
  delete_recursive_allowed = var.delete_recursive_allowed
  name                     = data.cloudfoundry_space.space.name
  org                      = data.cloudfoundry_org.org.id
}

###
# SES instance
###

data "cloudfoundry_service" "ses" {
  name = "datagov-smtp"
}

resource "cloudfoundry_service_instance" "ses" {
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
