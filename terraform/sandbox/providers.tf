terraform {
  required_version = "~> 1.7"
  required_providers {
    cloudfoundry = {
      source  = "cloudfoundry-community/cloudfoundry"
      version = "0.53.1"
    }
  }

  backend "s3" {
    bucket       = "cg-6b759c13-6253-4a64-9bda-dd1f620185b0"
    key          = "api.tfstate.sandbox"
    encrypt      = "true"
    region       = "us-gov-west-1"
    use_lockfile = "true"
  }
}

provider "cloudfoundry" {
  api_url      = "https://api.fr.cloud.gov"
  user         = var.cf_user
  password     = var.cf_password
  app_logs_max = 30
}
