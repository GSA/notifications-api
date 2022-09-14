terraform {
  required_version = "~> 1.0"
  required_providers {
    cloudfoundry = {
      source  = "cloudfoundry-community/cloudfoundry"
      version = "0.15.5"
    }
  }

  backend "s3" {
    bucket  = "cg-31204bcc-aae3-4cd3-8b59-5055a338d44f"
    key     = "api.tfstate.stage"
    encrypt = "true"
    region  = "us-gov-west-1"
    profile = "notify-terraform-backend"
  }
}
