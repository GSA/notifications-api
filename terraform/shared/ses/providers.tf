terraform {
  required_version = "~> 1.7"
  required_providers {
    cloudfoundry = {
      source  = "cloudfoundry/cloudfoundry"
      version = "1.9.0"
    }
    cfcommunity = {
      source  = "cloudfoundry-community/cloudfoundry"
      version = "0.53.1"
    }
  }
}

# Official provider (should be default but aliased for now)
provider "cloudfoundry" {
  alias    = "official"
  api_url  = "https://api.fr.cloud.gov"
  user     = var.cf_user
  password = var.cf_password
}

# Community provider (should be aliased but default for now)
provider "cfcommunity" {
  api_url      = "https://api.fr.cloud.gov"
  user         = var.cf_user
  password     = var.cf_password
  app_logs_max = 30
}
