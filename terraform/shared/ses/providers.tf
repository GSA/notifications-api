terraform {
  required_version = "~> 1.7"
  required_providers {

    cfcommunity = {
      source  = "cloudfoundry-community/cloudfoundry"
      version = "0.53.1"
    }
  }
}


# Community provider (should be aliased but default for now)
provider "cfcommunity" {
  api_url      = "https://api.fr.cloud.gov"
  user         = var.cf_user
  password     = var.cf_password
  app_logs_max = 30
}
