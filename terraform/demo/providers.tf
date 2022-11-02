terraform {
  required_version = "~> 1.0"
  required_providers {
    cloudfoundry = {
      source  = "cloudfoundry-community/cloudfoundry"
      version = "0.15.5"
    }
  }

  backend "s3" {
    bucket  = "TKTK"
    key     = "api.tfstate.prod"
    encrypt = "true"
    region  = "us-gov-west-1"
    profile = "notify-terraform-backend"
  }
}
