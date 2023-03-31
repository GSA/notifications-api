locals {
  cf_org_name      = "gsa-tts-benefits-studio-prototyping"
  cf_space_name    = "notify-local-dev"
  recursive_delete = true
  key_name         = "${var.username}-api-dev-key"
}

module "csv_upload_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.2.0"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  name             = "${var.username}-csv-upload-bucket"
}
resource "cloudfoundry_service_key" "csv_key" {
  name             = local.key_name
  service_instance = module.csv_upload_bucket.bucket_id
}

module "contact_list_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.2.0"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  name             = "${var.username}-contact-list-bucket"
}
resource "cloudfoundry_service_key" "contact_list_key" {
  name             = local.key_name
  service_instance = module.contact_list_bucket.bucket_id
}

data "cloudfoundry_space" "staging" {
  org_name = local.cf_org_name
  name     = "notify-staging"
}

data "cloudfoundry_service_instance" "ses_email" {
  name_or_id = "notify-api-ses-staging"
  space      = data.cloudfoundry_space.staging.id
}
resource "cloudfoundry_service_key" "ses_key" {
  name             = local.key_name
  service_instance = data.cloudfoundry_service_instance.ses_email.id
  params_json = jsonencode({
    source_ips = [var.source_ip]
  })
}

data "cloudfoundry_service_instance" "sns_sms" {
  name_or_id = "notify-api-sns-staging"
  space      = data.cloudfoundry_space.staging.id
}
resource "cloudfoundry_service_key" "sns_key" {
  name             = local.key_name
  service_instance = data.cloudfoundry_service_instance.sns_sms.id
  params_json = jsonencode({
    source_ips = [var.source_ip]
  })
}

locals {
  credentials = <<EOM

#############################################################
# CSV_UPLOAD_BUCKET
CSV_BUCKET_NAME=${cloudfoundry_service_key.csv_key.credentials.bucket}
CSV_AWS_ACCESS_KEY_ID=${cloudfoundry_service_key.csv_key.credentials.access_key_id}
CSV_AWS_SECRET_ACCESS_KEY=${cloudfoundry_service_key.csv_key.credentials.secret_access_key}
CSV_AWS_REGION=${cloudfoundry_service_key.csv_key.credentials.region}
# CONTACT_LIST_BUCKET
CONTACT_BUCKET_NAME=${cloudfoundry_service_key.contact_list_key.credentials.bucket}
CONTACT_AWS_ACCESS_KEY_ID=${cloudfoundry_service_key.contact_list_key.credentials.access_key_id}
CONTACT_AWS_SECRET_ACCESS_KEY=${cloudfoundry_service_key.contact_list_key.credentials.secret_access_key}
CONTACT_AWS_REGION=${cloudfoundry_service_key.contact_list_key.credentials.region}
# SES_EMAIL
SES_AWS_ACCESS_KEY_ID=${cloudfoundry_service_key.ses_key.credentials.smtp_user}
SES_AWS_SECRET_ACCESS_KEY=${cloudfoundry_service_key.ses_key.credentials.secret_access_key}
SES_AWS_REGION=${cloudfoundry_service_key.ses_key.credentials.region}
SES_DOMAIN_ARN=${cloudfoundry_service_key.ses_key.credentials.domain_arn}
# SNS_SMS
SNS_AWS_ACCESS_KEY_ID=${cloudfoundry_service_key.sns_key.credentials.aws_access_key_id}
SNS_AWS_SECRET_ACCESS_KEY=${cloudfoundry_service_key.sns_key.credentials.aws_secret_access_key}
SNS_AWS_REGION=${cloudfoundry_service_key.sns_key.credentials.region}
EOM
}

resource "null_resource" "output_creds_to_env" {
  triggers = {
    always_run = timestamp()
  }
  provisioner "local-exec" {
    working_dir = "../.."
    command     = "echo \"${local.credentials}\" >> .env"
  }
}
