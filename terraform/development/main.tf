locals {
  cf_org_name   = "gsa-tts-benefits-studio"
  cf_space_name = "notify-local-dev"
  key_name      = "${var.username}-api-dev-key"
}

module "csv_upload_bucket" {
  source = "github.com/GSA-TTS/terraform-cloudgov//s3?ref=v1.0.0"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${var.username}-csv-upload-bucket"
}
resource "cloudfoundry_service_key" "csv_key" {
  name             = local.key_name
  service_instance = module.csv_upload_bucket.bucket_id
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
